# Pilot Access — Shared Login Credentials

This document lists the shared login accounts for the QMS GenAI Platform
pilot deployed on Render. Any teammate can use these credentials without
raising a request. For a dedicated account, follow the **request access**
flow at the bottom of this page.

> ⚠️ **These are pilot credentials, not production.** Rotate them via
> Render → Environment tab before any customer-facing use. Never share
> this file outside the pilot team.

---

## Shared accounts (created at container startup)

| Username | Default password | Role | What they can do |
|---|---|---|---|
| `admin` | `QMSAdmin@2026` | **admin** | Everything — approve/reject CAPAs, manage users, run batch agent, access audit trail |
| `quality` | `QMSQuality@2026` | quality | Create records, draft CAPAs, view all data. No approvals. |
| `reviewer` | `QMSReviewer@2026` | quality | Same as `quality`. Provided so two people can log in as different reviewers during a demo. |
| `demo` | `QMSDemo@2026` | user | Read-only-ish demo account. Sees only its own records. Safe to share with customer prospects. |

**Login URL:** your Render service URL (e.g. `https://qms-web-xxxx.onrender.com`)

The bootstrap script (`scripts/bootstrap_pilot_users.py`) runs on every
container start. It creates missing users **and refreshes existing users'
password + role from the env vars** — so rotating a password is just a
Render env-var change followed by a redeploy, never a shell command.

---

## How passwords are set

Render loads passwords in this order:

1. Env var in Render → Environment tab (e.g. `ADMIN_PASSWORD`) — **wins if set**
2. Default in `scripts/bootstrap_pilot_users.py` — used if env var is empty

To rotate a password:

1. Render → `qms-web` → **Environment** tab
2. Add/edit the relevant `ADMIN_PASSWORD` / `QUALITY_PASSWORD` / `REVIEWER_PASSWORD` / `DEMO_PASSWORD`
3. Click **Save Changes** — Render redeploys, the bootstrap script picks up the new value on next boot
4. Update this doc

---

## Requesting a personal account

**Step 1** — On the login page, click **Register** (bottom of the form).

**Step 2** — Fill:
- Username (letters/numbers/dashes, no spaces)
- Full name
- Email
- Password (must be ≥ 12 chars with upper/lower/digit/symbol per policy)

**Step 3** — Wait for the admin (`admin@…` above) to approve you at
`/admin/manage-users`. You will not be able to log in until approval.

**Step 4** — Ping the admin owner (Shashikanth) directly on Teams/Slack
to fast-track approval. He can also assign you a role higher than the
default `user`.

---

## What each role can do (from `auth/users.py`)

| Capability | admin | quality | user |
|---|---|---|---|
| Login | ✅ | ✅ | ✅ |
| See all quality records | ✅ | ✅ | Own only |
| Create records | ✅ | ✅ | ✅ |
| Upload records | ✅ | ✅ | ✅ |
| Generate CAPA drafts | ✅ | ✅ | Own records only |
| Save CAPA to workflow | ✅ | ✅ | Own records only |
| **Approve / Reject CAPA** | ✅ | ❌ | ❌ |
| **Run batch agent** | ✅ | ❌ | ❌ |
| Approve/reject user registrations | ✅ | ❌ | ❌ |
| Change user roles | ✅ | ❌ | ❌ |

The dashboard hides buttons the current user can't use, so a `quality`
or `user` account still gets a clean UI.

---

## Security notes (before this goes to a real customer)

The defaults above are **shared team credentials**, which are fine for
an internal pilot demo but **not** for anything customer-facing. Before
a customer / audit review:

1. Set strong random `*_PASSWORD` env vars in Render (32+ chars each)
2. Rotate them via Render dashboard — **do not commit them to git**
3. Delete or disable the `demo` account after the demo call
4. Enable the audit trail review in `admin/audit`
5. Set `BOOTSTRAP_PILOT_USERS=false` and instead create per-user accounts
   through the /register flow, so the audit log names the real signer
   (Part 11 §11.10(d) — unique identification)
6. Turn on multi-factor (currently a follow-up work item — not yet
   implemented in the app)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Login page accepts creds then redirects back to login | Cookie issue — hard-refresh (Ctrl+Shift+R), clear site cookies |
| "Invalid username or password" for `admin` | The bootstrap script didn't run. Check Render logs for `[bootstrap]` lines. If absent, verify `BOOTSTRAP_PILOT_USERS=true` in Environment. |
| "Account pending approval" after login | You registered via /register — need admin to approve you. Ping Shashikanth. |
| `admin` password no longer works after redeploy | You (or someone) set `ADMIN_PASSWORD` in Render Environment. Check that tab. |
| Wanted 3 more test accounts for a specific customer | Register them via /register → admin approves → they have `user` role. If you want `quality` role, admin can bump the role at /admin/manage-users. |

---

## Reference

- Bootstrap script: `scripts/bootstrap_pilot_users.py`
- Env-var wiring: `render.yaml` (search for `BOOTSTRAP_PILOT_USERS`)
- Role definitions: `auth/users.py` → class `User`, methods `is_admin`, `can_approve_capa`, `sees_all_records`
- Registration flow: `routes/auth.py` → `page_register` handler
