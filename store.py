"""Optimistically update a record and append its immutable audit snapshot atomically."""

import json
import os
import sqlite3
from engine import Error


class Local:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS records (pk TEXT, sk TEXT, v INTEGER, body TEXT, PRIMARY KEY(pk,sk))"
        )

    def get(self, pk, sk):
        row = self.db.execute(
            "SELECT body FROM records WHERE pk=? AND sk=?", (pk, sk)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def rows(self, pk):
        return [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT body FROM records WHERE pk=? ORDER BY sk", (pk,)
            )
        ]

    def put(self, pk, sk, body, expected, audit=None):
        try:
            with self.db:
                if not expected:
                    self.db.execute(
                        "INSERT INTO records VALUES(?,?,?,?)",
                        (pk, sk, 1, json.dumps(body)),
                    )
                else:
                    updated = self.db.execute(
                        "UPDATE records SET v=?,body=? WHERE pk=? AND sk=? AND v=?",
                        (expected + 1, json.dumps(body), pk, sk, expected),
                    )
                    if not updated.rowcount:
                        raise Error("Record changed. Reload before saving.", 409)
                if audit:
                    self.db.execute(
                        "INSERT INTO records VALUES(?,?,1,?)",
                        (
                            "history#" + pk + "#" + sk,
                            str(expected + 1).zfill(10),
                            json.dumps(audit),
                        ),
                    )
        except sqlite3.IntegrityError:
            raise Error("Record already exists. Reload before saving.", 409)


class Dynamo:
    def __init__(self):
        import boto3

        self.client = boto3.client("dynamodb")
        self.table = os.environ["TABLE_NAME"]

    def key(self, pk, sk):
        return {"pk": {"S": pk}, "sk": {"S": sk}}

    def get(self, pk, sk):
        item = self.client.get_item(
            TableName=self.table, Key=self.key(pk, sk), ConsistentRead=True
        ).get("Item")
        return json.loads(item["body"]["S"]) if item else None

    def rows(self, pk):
        args = dict(
            TableName=self.table,
            KeyConditionExpression="pk = :p",
            ExpressionAttributeValues={":p": {"S": pk}},
            ConsistentRead=True,
        )
        result = []
        while True:
            page = self.client.query(**args)
            result.extend(json.loads(item["body"]["S"]) for item in page["Items"])
            if "LastEvaluatedKey" not in page:
                return result
            args["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def put(self, pk, sk, body, expected, audit=None):
        def put_item(p, s, obj, version):
            return {
                "TableName": self.table,
                "Item": {
                    **self.key(p, s),
                    "v": {"N": str(version)},
                    "body": {"S": json.dumps(obj)},
                },
                "ConditionExpression": "attribute_not_exists(pk)",
            }

        main = put_item(pk, sk, body, expected + 1)
        if expected:
            main.update(
                ConditionExpression="v = :v",
                ExpressionAttributeValues={":v": {"N": str(expected)}},
            )
        ops = [{"Put": main}]
        if audit:
            ops.append(
                {
                    "Put": put_item(
                        "history#" + pk + "#" + sk,
                        str(expected + 1).zfill(10),
                        audit,
                        1,
                    )
                }
            )
        try:
            self.client.transact_write_items(TransactItems=ops)
        except self.client.exceptions.TransactionCanceledException as exc:
            if any(
                x.get("Code") == "ConditionalCheckFailed"
                for x in exc.response.get("CancellationReasons", [])
            ):
                raise Error("Record changed. Reload before saving.", 409)
            raise
