"""Same-origin web app, hosted by API Gateway/Lambda or a loopback development server."""

import base64
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit
from engine import Error, email, require, now, words
from service import run, role
from store import Dynamo, Local

PUBLIC = Path(__file__).parent / "public"
AWS = bool(os.environ.get("TABLE_NAME"))
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}
STORE = None


def storage():
    global STORE
    if STORE is None:
        STORE = Dynamo() if AWS else Local(os.environ.get("LOCAL_DB", ".pipc.sqlite"))
    return STORE


def cognito(action, **args):
    import boto3
    from botocore.exceptions import ClientError

    try:
        return getattr(boto3.client("cognito-idp"), action)(**args)
    except ClientError as exc:
        errors = {
            "TooManyRequestsException": ("Too many attempts. Try again later.", 429),
            "UserNotConfirmedException": ("Confirm your email before signing in.", 403),
            "InvalidPasswordException": (
                "Use at least 12 characters with upper and lower case, a number and a symbol.",
                400,
            ),
            "CodeMismatchException": ("The confirmation code did not match.", 400),
        }
        message, code = errors.get(
            exc.response["Error"]["Code"],
            ("Authentication failed. Check your credentials or invitation.", 401),
        )
        raise Error(message, code)


def authenticate(token):
    require(token, "Sign in to your team workspace.", 401)
    if AWS:
        profile = cognito("get_user", AccessToken=token)
        # Cognito validated this token. Also bind it to our exact user pool and app.
        try:
            part = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        except (ValueError, IndexError):
            raise Error("Invalid session.", 401)
        issuer = (
            "https://cognito-idp."
            + os.environ["AWS_REGION"]
            + ".amazonaws.com/"
            + os.environ["POOL_ID"]
        )
        require(
            claims.get("iss") == issuer
            and claims.get("client_id") == os.environ["CLIENT_ID"]
            and claims.get("token_use") == "access",
            "Invalid session.",
            401,
        )
        attrs = {i["Name"]: i["Value"] for i in profile["UserAttributes"]}
        require(attrs.get("email_verified") == "true", "Verify your email.", 403)
        return email(attrs["email"])
    import time

    data = storage().get("sessions", hashlib.sha256(token.encode()).hexdigest())
    require(data and data["until"] > time.time(), "Sign in again.", 401)
    return data["email"]


def remember_registration(store, address, name, signed_up_at):
    profile = {"email": address, "name": name, "signedUpAt": signed_up_at}
    try:
        store.put("registrations", address, profile, 0)
    except Error as exc:
        if exc.status != 409 or not store.get("registrations", address):
            raise


def access(op, data):
    store = storage()
    address = email(data.get("email", ""))
    member = role(store, address)
    require(
        member and member["role"] != "Disabled",
        "An administrator must grant access to this email.",
        403,
    )
    password = data.get("password", "")
    require(isinstance(password, str) and len(password) <= 256, "Invalid password.")
    if op == "signup":
        name = words(data.get("name", ""), 100)
        joined = now()
    if AWS:
        appid = os.environ["CLIENT_ID"]
        if op == "signup":
            cognito(
                "sign_up",
                ClientId=appid,
                Username=address,
                Password=password,
                UserAttributes=[dict(Name="email", Value=address)]
                + ([dict(Name="name", Value=name)] if name else []),
            )
            remember_registration(store, address, name, joined)
            return dict(confirm=True), None
        if op == "confirm":
            cognito(
                "confirm_sign_up",
                ClientId=appid,
                Username=address,
                ConfirmationCode=str(data.get("code", "")),
            )
            return dict(confirmed=True), None
        if op == "resend":
            cognito("resend_confirmation_code", ClientId=appid, Username=address)
            return dict(confirm=True), None
        auth = cognito(
            "initiate_auth",
            ClientId=appid,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": address, "PASSWORD": password},
        )
        token = auth.get("AuthenticationResult", {}).get("AccessToken")
        require(
            token and authenticate(token) == address,
            "Email verification required.",
            401,
        )
        if not store.get("registrations", address):
            # Recover an older or partially registered account from Cognito's own creation record.
            account = cognito(
                "admin_get_user", UserPoolId=os.environ["POOL_ID"], Username=address
            )
            attrs = {a["Name"]: a["Value"] for a in account["UserAttributes"]}
            remember_registration(
                store,
                address,
                attrs.get("name", ""),
                account["UserCreateDate"].isoformat(),
            )
    else:
        import time

        if op == "signup":
            require(len(password) >= 12, "Use at least 12 characters.")
            salt = secrets.token_bytes(16)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
            store.put(
                "accounts",
                address,
                dict(
                    salt=salt.hex(), digest=digest.hex(), name=name, signedUpAt=joined
                ),
                0,
            )
            remember_registration(store, address, name, joined)
            return dict(confirmed=True), None
        require(op == "login", "Email verification is provided in the AWS environment.")
        acct = store.get("accounts", address)
        require(
            acct
            and hmac.compare_digest(
                hashlib.pbkdf2_hmac(
                    "sha256", password.encode(), bytes.fromhex(acct["salt"]), 600000
                ).hex(),
                acct["digest"],
            ),
            "Email or password incorrect.",
            401,
        )
        if not store.get("registrations", address):
            remember_registration(
                store, address, acct.get("name", ""), acct.get("signedUpAt")
            )
        token = secrets.token_urlsafe(40)
        store.put(
            "sessions",
            hashlib.sha256(token.encode()).hexdigest(),
            dict(email=address, until=time.time() + 3600),
            0,
        )
    return dict(ok=True), token


def request(method, path, headers, body):
    out = dict(HEADERS)
    try:
        if method == "GET":
            assets = {
                "/": "index.html",
                **{"/" + f.name: f.name for f in PUBLIC.iterdir() if f.is_file()},
            }
            require(path in assets, "File not found.", 404)
            file = PUBLIC / assets[path]
            out["Content-Type"] = (
                mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            )
            return 200, out, file.read_text()
        require(method == "POST" and path.startswith("/api/"), "Route not found.", 404)
        require(
            headers.get("content-type", "").split(";")[0] == "application/json",
            "JSON required.",
            415,
        )
        require(len(body) <= 64000, "Request too large.", 413)
        data = json.loads(body or "{}")
        require(isinstance(data, dict), "Expected an object.")
        op = path[5:]
        cookies = SimpleCookie()
        cookies.load(headers.get("cookie", ""))
        token = cookies["pipc"].value if "pipc" in cookies else ""
        expiry = None
        if op in ("login", "signup", "confirm", "resend"):
            result, token = access(op, data)
            if token:
                expiry = 3600
        elif op == "logout":
            if token and AWS:
                try:
                    cognito("global_sign_out", AccessToken=token)
                except Error as e:
                    if e.status != 401:
                        raise
            elif token and storage().get(
                "sessions", hashlib.sha256(token.encode()).hexdigest()
            ):
                storage().put(
                    "sessions",
                    hashlib.sha256(token.encode()).hexdigest(),
                    {"until": 0},
                    1,
                )
            token, expiry, result = "", 0, {"ok": True}
        else:
            result = run(storage(), authenticate(token), op, data)
        if expiry is not None:
            out["Set-Cookie"] = (
                f"pipc={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={expiry}"
                + ("; Secure" if AWS else "")
            )
        code = 200
    except (Error, KeyError, TypeError, json.JSONDecodeError) as exc:
        code = exc.status if isinstance(exc, Error) else 400
        result = {"error": str(exc) if isinstance(exc, Error) else "Invalid request."}
    out["Content-Type"] = "application/json"
    return code, out, json.dumps(result)


def handler(event, context):
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    headers["cookie"] = "; ".join(event.get("cookies", [])) or headers.get("cookie", "")
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body)
    code, headers, body = request(
        event["requestContext"]["http"]["method"], event["rawPath"], headers, body
    )
    cookie = headers.pop("Set-Cookie", None)
    return dict(
        statusCode=code, headers=headers, cookies=[cookie] if cookie else [], body=body
    )


if __name__ == "__main__":
    require(not AWS, "Use Lambda for AWS deployments.")
    os.environ.setdefault("ADMIN_EMAIL", "admin@pipc.test")

    class LocalWeb(BaseHTTPRequestHandler):
        def do_GET(self):
            length = int(self.headers.get("Content-Length", 0))
            if length > 64000:
                self.send_error(413)
                return
            code, headers, body = request(
                self.command,
                urlsplit(self.path).path,
                {k.lower(): v for k, v in self.headers.items()},
                self.rfile.read(length),
            )
            self.send_response(code)
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body.encode())

        do_POST = do_GET

    port = int(os.environ.get("PORT", 8765))
    print(
        f"PIPC development workspace: http://127.0.0.1:{port}  |  Administrator: {os.environ['ADMIN_EMAIL']}",
        flush=True,
    )
    HTTPServer(("127.0.0.1", port), LocalWeb).serve_forever()
