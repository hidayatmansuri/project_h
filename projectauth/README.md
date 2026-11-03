# projectauth — Reusable Authentication & Per-App Authorization for Django

`projectauth` is a reusable, production-grade Django authentication and per-app authorization app built for `project-h`. It enforces a strict **default-deny** security posture: any installed app not explicitly listed in `PROJECTAUTH_PUBLIC_APPS` is protected automatically with **no per-view edits**.

---

## Architecture Overview

```
                      +-----------------------------+
                      |       Incoming Request      |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   ProjectAuthMiddleware     |
                      +--------------+--------------+
                                     |
             +-----------------------+-----------------------+
             |                                               |
             v                                               v
    [ Public App or Path ]                         [ Protected App ]
(e.g., home, cv, static, /auth/*)                            |
             |                                               v
             |                                     Is user authenticated?
             |                                       /               \
             |                                     No                Yes
             |                                     /                   \
             |                           Redirect to Login       Has active grant
             |                        (or JSON 401 for API)     for protected app?
             |                                                   /              \
             |                                                 No               Yes
             |                                                 /                  \
             |                                       Redirect to Pending     Check HTTP Method vs
             |                                       or Access Request       Grant Level (read_only
             |                                      (or JSON 403 for API)    blocks POST/PUT/DELETE)
             |                                                                     /          \
             |                                                                Denied (403)   Allowed
             v                                                                                 v
     Process View <----------------------------------------------------------------------------+
```

### Core Primitives & Technologies
- **User Identity**: Preserves Django's built-in `django.contrib.auth.models.User` (Decision D1 / Constraint C4). Extends it with a 1-to-1 [`UserProfile`](file:///d:/project-h/project_h/projectauth/models.py#L20-L126).
- **Authentication**: Case-insensitive email or username sign-in via [`EmailOrUsernameBackend`](file:///d:/project-h/project_h/projectauth/backends.py#L18-L65).
- **Brute-Force Protection**: Integrated with `django-axes` (5 failures per identifier + IP, 15-minute lockout).
- **Session Management**: Dual-tier idle timeout middleware ([`IdleTimeoutMiddleware`](file:///d:/project-h/project_h/projectauth/middleware.py#L22-L78)): 30 minutes for administrators, 12 hours for regular users, plus 10-minute sudo re-authentication (`/auth/reauth/`) for sensitive actions.
- **Cryptography**:
  - **Argon2id**: Password hashing (`Argon2PasswordHasher` first in `PASSWORD_HASHERS`).
  - **AES-256-GCM**: Field-level encryption at rest for sensitive data (TOTP secrets, backup codes, invite tokens, email change payloads) with key rotation support (`kid1:...`).
  - **HMAC-SHA-256**: Constant-time token and one-time code hashing (`compare_digest`).
  - **Zero SMS / Zero Paid Services**: Second factors are standard RFC 6238 TOTP (offline authenticator apps), 6-digit email codes, and Crockford Base32 recovery codes.

---

## Settings Reference

The following settings configure `projectauth` in `project_h/settings.py` (all overridable via `.env`):

| Setting | Default | Description |
|---|---|---|
| `PROJECTAUTH_PUBLIC_APPS` | `['home', 'cv']` | List of Django app labels accessible to anonymous visitors without authentication. |
| `PROJECTAUTH_ENCRYPTION_KEYS` | `""` | Comma-delimited list of `kid:base64key` strings used for AES-256-GCM data encryption. The first key is used for new encryptions. |
| `PROJECTAUTH_SITE_NAME` | `"project-h"` | Site name used in emails and page titles. |
| `PROJECTAUTH_BASE_URL` | `"http://127.0.0.1:8000"` | Base URL used to construct absolute verification and password reset links. |
| `PROJECTAUTH_ADMIN_NOTIFY_EMAILS` | `[]` | List of email addresses to alert upon new user registrations and access requests. |
| `PROJECTAUTH_MAX_EMAILS_PER_DAY` | `300` | Hard daily budget guard preventing the system from exceeding Gmail SMTP free quotas. |
| `PROJECTAUTH_HIBP_CHECK` | `False` | When True, queries the HaveIBeenPwned k-anonymity API to reject compromised passwords. |
| `PROJECTAUTH_PASSWORD_MIN_LENGTH`| `12` | Minimum required password length. |
| `PROJECTAUTH_ADMIN_IDLE_TIMEOUT_MIN` | `30` | Minutes of inactivity before an administrator's session expires. |
| `PROJECTAUTH_USER_IDLE_TIMEOUT_HOURS` | `12` | Hours of inactivity before a regular user's session expires. |
| `PROJECTAUTH_REQUIRE_2FA_FOR_ADMINS` | `True` | Forces all admin users to enroll in 2FA before accessing console views. |
| `PROJECTAUTH_REQUIRE_2FA_FOR_ALL` | `False` | When True, requires all users to enroll in 2FA. |

---

## Management CLI Commands

### 1. `projectauth_sync_apps`
Synchronizes installed Django apps into the `ProtectedApp` registry table. Automatically assigns human-readable names and icons. Runs automatically on `post_migrate`.
```powershell
python manage.py projectauth_sync_apps
```

### 2. `projectauth_check`
Audits and classifies every URL pattern in the project as `public`, `protected`, or `unclassified`. Exits with non-zero status if any route is unclassified.
```powershell
python manage.py projectauth_check
```

### 3. `projectauth_init_admin`
Bootstraps or recovers administrator access directly from the terminal without interactive prompts. Supports setting initial passwords and resetting 2FA.
```powershell
# Create or promote admin
python manage.py projectauth_init_admin --username=admin --email=admin@example.com --password="SecurePassword!123"

# Reset 2FA factors for a locked-out admin
python manage.py projectauth_init_admin --username=admin --reset-2fa
```

### 4. `projectauth_rotate_keys`
Re-encrypts all stored secrets (TOTP seeds, recovery codes, invitations, email tokens) from older encryption keys to the active primary key.
```powershell
python manage.py projectauth_rotate_keys
```

### 5. `projectauth_purge_audit`
Purges audit log records older than a specified number of days (default: 365) to maintain compliance and database performance.
```powershell
python manage.py projectauth_purge_audit --older-than-days=365
```

### 6. `projectauth_cleanup`
Prunes expired verification tokens, used password reset tokens, expired trusted devices, and stale session records. Recommended to run daily via cron or scheduler.
```powershell
python manage.py projectauth_cleanup
```

---

## How to Add a New App in 3 Steps

Because `projectauth` uses a centralized middleware architecture, future apps are protected **by default with zero view modifications**:

1. **Create the app and add it to `INSTALLED_APPS`** in `project_h/settings.py`:
   ```python
   INSTALLED_APPS = [
       ...
       'mynewapp',
       'projectauth.apps.ProjectAuthConfig',
   ]
   ```

2. **Run migrations or sync apps**:
   ```powershell
   python manage.py migrate
   # or:
   python manage.py projectauth_sync_apps
   ```

3. **Verify route protection**:
   ```powershell
   python manage.py projectauth_check
   ```
   *Result*: `mynewapp` is instantly registered as a `ProtectedApp`. Anonymous visitors are redirected to `/auth/login/`, and authenticated users without an `AppAccess` grant are redirected to `/auth/pending/` with an "Access Request" button. API endpoints receive JSON 401/403 automatically.

---

## Operational Runbooks

### Runbook 1: Lost Sole Administrator Access
If the only administrator account is locked out or loses credentials:
1. Access the host or container terminal.
2. Execute the CLI initialization command:
   ```powershell
   python manage.py projectauth_init_admin --username=admin --password="TemporaryNewPassword!123" --reset-2fa
   ```
3. Sign in at `/auth/login/` with the new password.
4. Immediately navigate to `/auth/account/` and configure a new authenticator app (TOTP) and save fresh recovery codes.

### Runbook 2: User Lost 2FA Device
When a user loses their authenticator app:
1. **Self-Service with Recovery Codes**: At the 2FA challenge screen, the user clicks *"Use a recovery code"* and enters one of their ten 10-character Crockford Base32 backup codes. Once logged in, they can regenerate codes or re-bind their TOTP app.
2. **Email Fallback**: If email fallback is enabled, the user clicks *"Send code to my email"* to receive a short-lived 6-digit code.
3. **Administrator Reset**: An administrator can visit `/auth/console/users/<id>/` and click *"Reset 2FA"*, or run:
   ```powershell
   python manage.py projectauth_init_admin --username=<username> --reset-2fa
   ```

### Runbook 3: Secret Key Rotation (Zero Downtime)
To rotate data encryption keys at rest without invalidating existing stored secrets:
1. Generate a new 32-byte URL-safe base64 key:
   ```powershell
   python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
   ```
2. In `.env`, prepend the new key to `PROJECTAUTH_ENCRYPTION_KEYS` (e.g., `kid2:<new_key>,kid1:<old_key>`).
3. Run key rotation to re-encrypt all records with `kid2`:
   ```powershell
   python manage.py projectauth_rotate_keys
   ```
4. Verify the output reports `rotated_count > 0` and `skipped_count = 0`.
5. Remove `kid1` from `PROJECTAUTH_ENCRYPTION_KEYS` in `.env`.

### Runbook 4: Gmail SMTP & Daily Email Quota Guard
`projectauth` is configured for Gmail SMTP using a Google Workspace / Gmail **App Password**:
1. In your Google Account: Enable **2-Step Verification**, go to **Security > App passwords**, and generate a 16-character password for "project-h".
2. In `.env`:
   ```ini
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=your-dedicated-address@gmail.com
   EMAIL_HOST_PASSWORD=your16charpassword
   DEFAULT_FROM_EMAIL=your-dedicated-address@gmail.com
   PROJECTAUTH_MAX_EMAILS_PER_DAY=300
   ```
3. The built-in email budget guard (`EmailBudgetCounter`) tracks all sent messages in the database. At 80% and 100% capacity, warning alerts are logged to `projectauth_security.log`. Once the budget is reached, further automated emails are blocked to prevent account suspension.

### Runbook 5: Sharing `utilitytracker` with Testers (Decision D3)
Per Decision D3, `utilitytracker` is a shared household dataset. **No owner field or schema modification is permitted**.
To let external testers inspect the application safely:
1. Have the tester sign up at `/auth/signup/` or issue an invite via `/auth/console/invites/`.
2. Go to `/auth/console/users/<id>/`.
3. In the **App Access** table for `utilitytracker`:
   - Set **Access Level** to **`read_only`**.
   - Set **Expires At** to the desired test end time (e.g., 7 days from now).
   - Click **Save**.
4. **Behavior**:
   - The tester can view all historical readings, consumption metrics, and charts.
   - Any attempt to submit new readings (`submit_reading`), add top-ups (`submit_topup`), or delete top-ups (`delete_topup`) is blocked with HTTP `403 Forbidden`.
   - After the expiration timestamp passes, access to the entire `/utility` route is blocked.

---

## Honest 256-Bit Cryptography Notes

`projectauth` employs industry-standard 256-bit cryptography, but administrators must understand what it **does** and **does not** protect:

### What It Protects
- **Data at Rest**: TOTP seeds, backup codes, email verification tokens, and invitation parameters stored in the database are encrypted using **AES-256-GCM** with unique 96-bit nonces. If a raw SQL database backup is leaked or stolen, the attacker cannot read TOTP secrets or access codes without the encryption key.
- **Integrity**: AES-GCM is an Authenticated Encryption with Associated Data (AEAD) cipher. Any tampering with ciphertexts in the database causes immediate authentication failure upon decryption.
- **Brute-Force Resistance**: Passwords are hashed with **Argon2id** (memory-hard, resistant to GPU/ASIC cracking). Codes and lookup tokens are hashed with **HMAC-SHA-256** and compared using constant-time string comparisons (`hmac.compare_digest`) to prevent timing attacks.

### What It Does NOT Protect
- **Compromised Host / Memory**: If the application server itself is compromised (e.g., an attacker achieves code execution or root access), the attacker can read environment variables (`PROJECTAUTH_ENCRYPTION_KEYS`) and inspect process memory. 256-bit encryption cannot protect keys from the machine executing the code.
- **Weak Passwords**: 256-bit encryption of TOTP secrets does not compensate for weak user passwords. Users must adhere to the 12-character minimum length and optional HaveIBeenPwned breach checks.
- **Client-Side Attacks**: Session cookies are protected with `HttpOnly`, `SameSite=Lax`, and `Secure` (in production), but malicious browser extensions or compromised endpoints can still capture credentials at input time.

