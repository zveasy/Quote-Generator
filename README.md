# PIPC Quote Studio

An internal quote workspace for Pawsitive Impact Pet Care. It covers inquiry review through the client's Meet & Greet decision. Target internal completion is December 21, 2026 and launch is January 1, 2027.

## Try it locally

Run `python3 -B app.py` with Python 3.9+ and open http://127.0.0.1:8765. Choose **Sign up**, enter `admin@pipc.test`, and create a local password of at least 12 characters. Then sign in. Use `ADMIN_EMAIL`, `PORT`, and `LOCAL_DB` to customize the loopback development instance. Local authentication simulates verified invitations and saves salted password hashes and sessions in an ignored SQLite file. Use synthetic client details for local evaluation.

1. The catalog opens with six editable plans from the supplied PIPC Quote Generator Info PDF. In **Pricing**, select a plan to update its rates, description and client reply contact. Custom plans are also supported. Select an existing version to add a new effective-dated version. Among versions with the same effective date, the most recently created applies.
2. In **Team**, grant access to a work email. Team members can prepare drafts and view the shared pipeline. Enable sending for individuals who can issue estimates and record delivery or responses. Administrators manage access, pricing, and overrides. The deployment administrator retains access.
3. Choose **Create a quote**. Enter client details and a TTP identifier if available. Save a draft at any point. Select a plan and enter the requested service dates, pets, quantity, travel, add-ons and notes. **Calculate estimate** previews the itemization. On a saved draft, **Review and issue** asks for confirmation and freezes the estimate.
4. **Print / Save PDF** opens the browser print dialog. Select Save as PDF and turn browser headers/footers off. **Copy email estimate** produces plain text. Send using the team's email client or a supported TTP conversation, then choose **Mark as sent**. A staff member records the client's acceptance or decline manually.
5. An acceptance requests a Meet & Greet. Shannon coordinates follow-up. Macayla retains control of availability, exceptions, staffing and scheduling. An expired estimate must be revised and issued again. Search by client name, email or TTP ID to find related quotes. **History** opens timestamped snapshots of drafts, issues, deliveries, revisions, and responses.

## Pricing and expiration decisions for review

The quote uses the plan effective on the issue date in the configured business time zone. Each issued version preserves its inputs, rates and line items. All dollar figures below are initial catalog values.

| Service | Calculation |
| --- | --- |
| Check-ins | For caretaker-to-client travel of 0–14, 15–29 or 30–45 minutes, a 20-minute visit costs $25/$30/$35. A 45-minute visit costs $35/$40/$45. Enter each visit’s local date and start time. Weekend or late night adds $10 per visit. Together they add $15. Late night starts after 7 p.m. and includes 9 p.m. A listed holiday adds $20 on top. |
| Overnight | Essential is $100/night and Premium is $120/night. The first six nights and first three dogs/cats use the base terms. Each night after six adds $10. Travel over 25 and up to 35 minutes adds $5 on every night. Small animal care adds $20/stay plus $5 per night after six. Chicken care adds $15/night. Dogs fill the included slots first, then cats. Each extra dog adds $10/night and each extra cat $5/night. Each listed holiday night adds $20. |
| Extended care | Two-hour minimum. The first hour costs $30/$35/$40 across the same three travel bands. Each additional hour costs $20. Fractional additional hours are prorated. |
| Wedding chaperoning | Two-hour minimum. One chaperone costs $65/hour. Two together cost $105/hour. |

Travel is entered in whole minutes from the caretaker’s home. The published ranges end at 45 minutes for check-ins/extended care and 35 for overnights. Wedding rates cover one or two chaperones. Requests outside these ranges require separate pricing. Overnight fees use the local date each night starts and exclude the checkout date. The sheet allows up to six nights per caretaker. Longer estimates include the extended-stay fees and leave staffing to Macayla.

Holiday dates are New Year’s Day, Easter Sunday, Memorial Day, July 4, Labor Day, Thanksgiving, Christmas Eve, Christmas Day and New Year’s Eve. Check-ins use the actual service date. Overnight fees apply once per qualifying night.

- An estimate issued December 1 is valid through December 8 in the business time zone. At the start of December 9 the application displays it as expired and rejects a response. Expiration and its timeline event are computed from the stored issue terms, including when the app was closed. Revisions retain earlier snapshots under the same quote number.

## Deploy to AWS in us-east-1

The AWS SAM template provisions an HTTPS API Gateway HTTP API, Python Lambda, an encrypted DynamoDB table with point-in-time recovery, and an email-verified Cognito user pool. Cognito owns production passwords. DynamoDB holds access grants, pricing versions, quotes and audit records. Server-side role checks run on each protected request. Conditional transactions commit a record and its audit snapshot together. Each session uses an HTTP-only, Secure, SameSite cookie with a one-hour lifetime.

Use the PIPC account's authenticated AWS CLI profile and the intended administrator's real work email. Configure AWS access on the deployment machine using SSO or a short-lived profile. No AWS secrets belong in the repository or browser. Install AWS SAM CLI before running these commands. Replace the example profile name and email.

```sh
python3 -B -m unittest discover -s tests -v
python3 scripts/package.py
sam validate --lint --region us-east-1
sam deploy --template-file template.yaml --stack-name pipc-quote-studio \
  --profile YOUR_PIPC_PROFILE --region us-east-1 --resolve-s3 \
  --capabilities CAPABILITY_IAM --confirm-changeset \
  --parameter-overrides AdminEmail=YOUR_ADMIN_EMAIL BusinessTimezone=America/New_York EnableStats=false
```

Open the stack's **WorkspaceUrl** output. Sign up with the bootstrap email, complete the Cognito email verification, then sign in. Add the real team and approved prices. EnableStats=true creates a private encrypted S3 bucket and enables an administrator to export aggregate quote counts by status. The export excludes client details. Deployment artifacts use SAM's separate packaging bucket. The table, pool and optional stats bucket are retained on stack deletion.

Before launch, verify account signup and verification email delivery in the target account, revoked access, quote persistence across sessions, mobile use, a downloaded PDF and the acceptance/expiration workflow. Review example estimates with Shannon and Macayla and confirm rates, fee stacking, sender rights, the business time zone, public contact and logo. The included paw-and-heart mark is proposed artwork.

## Time To Pet handoff

Time To Pet documents a **New Client Prospect Created** Zapier trigger that includes built-in fields and custom fields with Zapier Names. Its documentation also describes uploading a document through a client profile's Docs tab and sending a message with an attachment through the Conversation Feed. Sources: [Zapier integration](https://help.timetopet.com/en/articles/11547477-zapier-integration), [Documents](https://help.timetopet.com/en/articles/11547579-documents), [Client Conversation Feed](https://help.timetopet.com/en/articles/11547006-using-the-client-conversation-feed).

For the MVP, copy the prospect's details and available TTP identifier, generate and send the estimate, and manually attach the PDF to the correct profile when available. All quote actions are internal to Quote Studio. The application makes no TTP calls.

Before implementing automation, ask TTP support whether a public or partner API permits prospect lookup, stable client/prospect matching, updating fields or notes, uploading a profile document, and receiving signed webhooks. Ask which integrations beyond Zapier are officially supported, what authentication and account permissions apply, and how duplicate or converted prospects should be handled. These write and lookup capabilities remain unverified.

## Employee accounts

In **Team**, an administrator grants access to an employee’s individual work email and chooses their role and sending permission. The employee selects **Sign up**, enters their name and that email, chooses a password, and verifies their email in the AWS deployment. On later visits they select **Sign in** using the same email and password. **My account** shows the employee’s own details and access level. The shared quote pipeline remains available to authorized team members.

The administrator’s **Team** directory lists each authorized email, the registered name, role and sign-up time (displayed in the viewer’s local time). Granting access and registering an account are separate events. Signing in again or changing access preserves the original registration date. Older Cognito accounts recover their creation date on their next login. Older local accounts without a recorded date are labeled accordingly.
