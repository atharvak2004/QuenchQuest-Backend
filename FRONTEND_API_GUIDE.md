# QuenchQuest – Frontend API Integration Guide

Base URL: `http://127.0.0.1:8000` locally, or your deployed backend domain.
Interactive docs (try any endpoint): **`/api/docs/`** (Swagger) · raw OpenAPI schema: `/api/schema/`

All request and response bodies are JSON (`Content-Type: application/json`).

---

## 1. Two kinds of users, two kinds of tokens

| Who | Logs in with | Login endpoint | Used for |
|---|---|---|---|
| **Volunteer** (public website user, `User`) | email + password | `POST /api/auth/login/` | website features, campaigns (read), beneficiaries, donations |
| **Admin / Employee / Editor** (`SisUser`) | username + password | `POST /api/auth/sisuser/login/` | admin panel (see [ADMIN_PANEL_API_GUIDE.md](ADMIN_PANEL_API_GUIDE.md)) |

Both logins return two tokens:

- `token`: the access token, valid for **24 hours**. Send it on every protected call:
  ```
  Authorization: Bearer <token>
  ```
- `refresh`: valid for **30 days**. When a call returns `401`, exchange it at `POST /api/auth/token/refresh/` with body `{ "refresh": "<refresh>" }`. You get back a new `{ token, refresh }` pair; store both. If the refresh call also returns `401`, send the user to login.

Changing or resetting a password logs out every existing session, because the old tokens stop working.

Store which kind of user is logged in (`"volunteer"` or the `role` returned by the admin login) so the UI shows the right pages.

---

## 2. Response and error format

Successful responses vary per endpoint (shown below). Errors come in **three shapes**, so handle all of them:

```jsonc
{ "Error": "Email already registered." }          // custom errors (note the capital E)
{ "detail": "Authentication credentials were not provided." }   // 401 / 403 from DRF
{ "email": ["Enter a valid email address."] }     // field validation errors
```

Helper to turn any error into one string:

```js
export function errorMessage(data) {
  if (!data) return "Something went wrong.";
  if (typeof data === "string") return data;
  if (data.Error) return data.Error;
  if (data.detail) return data.detail;
  if (data.message) return data.message;
  const [field, msgs] = Object.entries(data)[0] || [];
  return field ? `${field}: ${[].concat(msgs).join(" ")}` : "Something went wrong.";
}
```

| Status | Meaning in this API |
|---|---|
| 200 / 201 | OK / created |
| 400 | Validation error, wrong OTP, wrong password (volunteer login), unverified email |
| 401 | Missing, invalid or expired token; wrong admin username/password |
| 403 | Logged in, but your role can't do this (e.g. employee deleting an employee) |
| 404 | Not found (user, employee, impact data) |

---

## 3. Recommended API client (axios)

```js
// src/api/client.js
import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL, // e.g. http://127.0.0.1:8000
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshing = null; // share one refresh call between parallel 401s

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;
    const refresh = localStorage.getItem("refresh");
    if (err.response?.status === 401 && refresh && !original._retried) {
      original._retried = true;
      try {
        refreshing ??= axios.post(`${api.defaults.baseURL}/api/auth/token/refresh/`, { refresh });
        const { data } = await refreshing;
        localStorage.setItem("token", data.token);
        localStorage.setItem("refresh", data.refresh);
        original.headers.Authorization = `Bearer ${data.token}`;
        return api(original);
      } catch {
        /* fall through to logout */
      } finally {
        refreshing = null;
      }
    }
    if (err.response?.status === 401) {
      ["token", "refresh", "userType"].forEach((k) => localStorage.removeItem(k));
      // window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);
```

Use `errorMessage(err.response?.data)` in your `catch` blocks.

---

## 4. Volunteer authentication flow (`/api/auth/`)

```
Register ──► OTP emailed ──► Verify OTP ──► Login ──► token
Forgot password ──► OTP emailed ──► Reset password
```

### Register — `POST /api/auth/register/` (public)
```json
{
  "name": "Riya Patil",
  "email": "riya@example.com",
  "phone": "9876543210",
  "gender": "female",
  "skills": "Teaching, Design",
  "location": "Pune",
  "availability": "Weekends",
  "password": "Secret@123"
}
```
Required: `name, email, phone, gender, skills, password`. `gender` is `male` | `female` | `other`.
**201** `{ "message": "Registration successful. OTP sent to email." }`
**400** `{ "Error": "Email already registered." }`

### Verify OTP — `POST /api/auth/verify-otp/` (public)
```json
{ "email": "riya@example.com", "otp": "123456" }
```
**200** `{ "message": "OTP verified successfully." }` — the volunteer also gets a welcome email with their Volunteer ID (`QQ001`, …).
**400** `{ "Error": "Invalid OTP." }` · **404** `{ "Error": "User not found." }`

### Login — `POST /api/auth/login/` (public)
```json
{ "email": "riya@example.com", "password": "Secret@123" }
```
**200**
```json
{
  "message": "Login successful.",
  "user": { "id": 5, "volunteer_id": "QQ005", "name": "...", "email": "...", "phone": "...",
            "gender": "...", "skills": "...", "location": "...", "availability": "..." },
  "token": "eyJhbGciOi...",
  "refresh": "eyJhbGciOi..."
}
```
**400** wrong password / `"Please verify your email first."` / `"User not found."` · **403** account deactivated by an admin
If the error is "Please verify your email first.", send the user to the OTP screen.

```js
const { data } = await api.post("/api/auth/login/", { email, password });
localStorage.setItem("token", data.token);
localStorage.setItem("refresh", data.refresh);
localStorage.setItem("userType", "volunteer");
```

### Resend OTP — `POST /api/auth/resend-otp/` (public)
`{ "email": "riya@example.com" }` → **200** `{ "message": "A new OTP has been sent to your email." }`
**400** already verified · **404** not registered · **429** asked again within 60 seconds (show the wait time from `Error`)

### My profile — `GET` / `PATCH /api/auth/me/` (volunteer token)
GET **200** `{ "id", "volunteer_id", "name", "email", "phone", "gender", "skills", "location", "availability", "is_verified", "created_at" }`
PATCH any of `name, phone, gender, skills, location, availability`. `email` can't be changed here. `gender` is `male` | `female` | `other` | `prefer_not_to_say`.

### Forgot password — `POST /api/auth/forgot-password/` (public)
`{ "email": "riya@example.com" }` → **200** `{ "message": "OTP sent successfully." }` · **404** if not registered

### Reset password — `POST /api/auth/reset-password/` (public)
`{ "email": "...", "otp": "123456", "new_password": "NewSecret@123" }` → **200** `{ "message": "Password reset successful." }`

---

## 5. Admin / Employee authentication (`/api/auth/`)

### Login — `POST /api/auth/sisuser/login/` (public)
```json
{ "username": "admin", "password": "Admin123" }
```
**200** `{ "token": "...", "refresh": "...", "id": 1, "role": "admin", "username": "admin", "modules": ["campaigns", "content", "inbox", "staff", "volunteers"] }`
`role` is `admin`, `employee_role` or `editor`. `modules` lists which admin-panel sections to show.
**401** `{ "Error": "Invalid username or password." }` · **403** deactivated, or locked for 15 minutes after 5 wrong passwords in a row

```js
const { data } = await api.post("/api/auth/sisuser/login/", { username, password });
localStorage.setItem("token", data.token);
localStorage.setItem("refresh", data.refresh);
localStorage.setItem("userType", data.role); // "admin" | "employee_role" | "editor"
```

### Change my password — `POST /api/auth/sisuser/change-password/` (any staff)
`{ "old_password": "...", "new_password": "at least 8 chars" }` → **200** `{ "message", "token", "refresh" }`. Store the new tokens; all other sessions are logged out.

### Dashboard access check — `GET /api/auth/dashboard/` (admin, employee)
**200** `{ "message": "Dashboard Access Granted", "user": "admin", "role": "admin" }`. Call this to check that a stored token still works.

### Profile — `GET /api/auth/profile/` and `PATCH /api/auth/profile/` (admin, employee)
GET **200** `{ "id": 1, "username": "...", "email": "...", "phone": "...", "location": "...", "choice": "admin" }`
PATCH (send only the fields to change): `{ "phone": "9999999999", "location": "Mumbai" }`
→ **200** `{ "message": "Profile updated successfully", "data": { ...profile } }`. `choice` (role) cannot be changed here.

### Create employee/admin — `POST /api/auth/sisuser/create/` (**admin only**)
```json
{ "username": "emp1", "email": "emp1@example.com", "phone": "9000000000",
  "location": "Pune", "password": "Emp@1234", "choice": "employee_role" }
```
**201** the created user (no password). **403** if you're not an admin.
> The very first admin has to be created by the backend team with `python manage.py createsuperuser`, then given `choice = admin` in Django admin (`/admin/`).

### List employees/admins — `GET /api/auth/sisuser/list/` (admin only)
**200** `[ { "id", "username", "email", "phone", "location", "choice" }, ... ]`

### Delete employee — `DELETE /api/auth/employee/delete/{id}/` (admin only)
**200** `{ "message": "User deleted successfully." }` · **404** `{ "Error": "Employee not found." }` (admins can't be deleted this way)

---

## 6. Admin dashboard – volunteers (`/api/dashboard/`, admin & employee token)

### List volunteers + stats — `GET /api/dashboard/volunteers/`
Query params: `page` (default 1), `page_size` (default 10, max 100), `search`.

Without `search` (paginated):
```json
{
  "total_volunteers": 120, "verified_users": 100, "unverified_users": 20,
  "male_volunteers": 50, "female_volunteers": 68, "new_users_today": 3,
  "volunteers": [ { "id": 1, "volunteer_id": "QQ001", "name": "...", "email": "...",
                    "gender": "female", "phone": "...", "skills": "...", "location": "...",
                    "availability": "...", "is_verified": true, "created_at": "2026-11-18T10:00:00+05:30" } ],
  "pagination": { "count": 120, "next": "http://.../?page=2", "previous": null }
}
```
With `search` (**not paginated**; it matches the *start* of name, email, phone, volunteer ID, gender, skills, location or availability): same stats + `"count"` + `"volunteers"`, no `pagination` key.

```js
const { data } = await api.get("/api/dashboard/volunteers/", { params: { page, page_size: 10, search } });
const rows = data.volunteers;
const total = data.pagination?.count ?? data.count;
```

### Create volunteer — `POST /api/dashboard/volunteers/`
Body like register, without `password`. The account is created already verified.
**201** `{ "message": "Volunteer created successfully.", "volunteer_id": "QQ121", "password": "riya9876" }`
Show the generated password to the admin once; it is the first name in lowercase plus the first 4 digits of the phone.

### Update volunteer — `PATCH /api/dashboard/volunteers/{id}/`
Any of `name, email, phone, gender, skills, location, availability, is_verified`.
**200** `{ "message": "Volunteer updated successfully.", "volunteer": { ... } }` · **400** `{ "Error": "Invalid data provided.", "errors": { ... } }`
`{id}` is the numeric `id`, **not** `volunteer_id` (`QQ001`).

### All users — `GET /api/dashboard/users/`
**200** `{ "total_users": 120, "users": [ ...same shape as volunteers... ] }`

---

## 7. Campaigns, beneficiaries, donations (`/api/dashboard/`)

These endpoints accept **either** a volunteer token **or** an admin/employee token.

| Endpoint | GET | POST |
|---|---|---|
| `/api/dashboard/campaigns/` | any logged-in user | admin/employee only |
| `/api/dashboard/beneficiaries/` | any logged-in user | any logged-in user |
| `/api/dashboard/donations/` | admin/employee: all · volunteer: **own only** | any logged-in user |

### Campaign
For website pages, use the public **`/api/website/campaigns/`** (section 8). It needs no login.
This older endpoint still works: volunteers see only published campaigns, and staff see every campaign that isn't archived. Its response is the admin shape, documented in [ADMIN_PANEL_API_GUIDE.md](ADMIN_PANEL_API_GUIDE.md). `is_active` has been replaced by `status` (`upcoming` | `active` | `completed`).

### Beneficiary
POST `{ "age": 12, "need": "School books", "location": "Pune", "status": "pending" }`
- With a volunteer token, `user` is set to the logged-in volunteer automatically.
- With an admin token you may pass `"user": <volunteer id>`, or leave it out.
- `status`: `pending` | `approved` | `helped`.

Response: `{ "id", "user", "user_name", "user_email", "age", "need", "location", "status", "created_at" }`

### Donation
POST `{ "amount": "500.00", "campaign": 4 }` with a volunteer token (donor = logged-in volunteer). `campaign` is optional and must be a published campaign.
With an admin token: `{ "amount": "500.00", "donor": <volunteer id> }` (donor is required).
GET accepts `?campaign=<id>`.
Response: `{ "id", "donor", "donor_name", "amount", "campaign", "campaign_title", "created_at" }`. `amount` comes back as a **string**, so use `Number(amount)` before doing maths with it.

> Edit and delete for these three live in the admin panel: `/api/admin/campaigns/`, `/api/admin/beneficiaries/` and `/api/admin/donations/`.

---

## 8. Public website content (`/api/website/`, no token)

Everything here is edited from the admin panel, so the website can stop hard-coding it. Only **published** items are returned; drafts and archived items never appear. These endpoints ignore any `Authorization` header, so a stale token can't break a public page.

Lists marked *paginated* return `{ count, next, previous, results }` and accept `?page=` and `?page_size=` (max 100; the default is 20).

| Endpoint | Returns |
|---|---|
| `GET /api/website/services/` *(paginated)* | Services in display order. `?show_on_home=true` for the home grid |
| `GET /api/website/services/{slug}/` | One service |
| `GET /api/website/projects/` *(paginated)* | Project cards. Filters: `?service=<slug or id>`, `?status=concept\|active\|completed\|paused`, `?featured=true` (home cards, in order), `?search=` |
| `GET /api/website/projects/{slug}/` | Full project brief: activities, phases, indicators, safeguards, gallery |
| `GET /api/website/projects/map/` | Map pins `[ { id, title, slug, status, service, location_name, latitude, longitude } ]` (not paginated) |
| `GET /api/website/stats/` | `{ volunteers, services, projects, people_benefited, communities_reached }` for the hero stats |
| `GET /api/website/impact/` | `[ { id, children_women_supported, skill_awareness_programs, communities_reached, date } ]`, newest first |
| `GET /api/website/our-impact/latest/` | The newest record by `date` · **404** if there is none |
| `GET /api/website/leadership/` | `[ { id, name, position, short_description, image, image_web, image_alt, display_order } ]` in display order |
| `GET /api/website/faqs/` *(paginated)* | `{ id, question, answer, display_order }` |
| `GET /api/website/settings/` | Contact email, phone and address; LinkedIn, Instagram, Facebook and YouTube URLs; `footer_tagline`; `get_involved_options` and `donate_focus_areas` (both `[ { title, description } ]`) |
| `GET /api/website/content-blocks/?prefix=about.` *(paginated)* | Blocks such as `about.vision` or `home.hero.headline`: `{ key, title, body, data, image, image_web, image_alt }`. Also `?keys=a,b` |
| `GET /api/website/content-blocks/{key}/` | One block |
| `GET /api/website/pages/{slug}/` | Legal pages (e.g. `privacy-policy`, `terms-and-conditions`). `body` is HTML |
| `GET /api/website/campaigns/` *(paginated)* | Campaigns. Filters: `?status=upcoming\|active\|completed`, `?featured=true` (for Donate / Get Involved), `?service=<slug or id>` |
| `GET /api/website/campaigns/{slug}/` | One campaign. Supports `?preview=` and the renamed-slug 301, like projects |
| `GET /api/website/program-cards/` | **Deprecated**, replaced by `/services/`. The existing cards were copied into Services by a migration |

Things to handle:

- **Lists are real JSON arrays** (`activities`, `beneficiaries`, `safeguards`, …), so you don't need to split strings any more.
- **Images:** use `cover_image_web` (a WebP of at most 1600 px) on the page and fall back to `cover_image` (the original). Always set `alt` from `cover_image_alt` / `image_alt`.
- **`people_benefited`** is `null` until an admin verifies the number. When it's `null`, show "Record pending".
- **Renamed slugs:** an old slug returns **301** `{ "redirect_slug": "new-slug" }`. Redirect the visitor to the new URL.
- **Draft previews:** the admin panel opens `/projects/{slug}?preview=<token>`. Pass `preview` through to the API (`GET /api/website/projects/{slug}/?preview=<token>`) to show the draft. A bad or expired token returns **403**.
- **Page HTML:** sanitise `body` (e.g. with DOMPurify) before rendering it with `dangerouslySetInnerHTML`.
- **Refresh hook:** if the website caches API responses, set `WEBSITE_REVALIDATE_URL` and `WEBSITE_REVALIDATE_SECRET` in the backend `.env`. After every content save the backend sends `POST {url}` with header `X-Revalidate-Secret: <secret>` and body `{ "model": "project", "slug": "clean-water" }`. Check the secret, then clear that page's cache.

### Campaigns on the website

Each campaign has these fields:
- **Basics:** `id`, `title`, `slug`, `summary`, `description`, `location_name`
- **Status and dates:** `status`, `start_date`, `end_date`
- **Images:** `cover_image`, `cover_image_web`, `cover_image_alt`, `share_image`
- **Fundraising:** `goal_amount`, `raised_amount`, `progress_percent`, `donor_count`
- **Volunteers:** `volunteer_count`, `allow_volunteers`
- **Links:** `service`, `service_title`, `service_slug`, `project`, `project_title`, `project_slug`
- **Display:** `is_featured`, `display_order`, `seo_title`, `seo_description`
- **Volunteer only:** `has_joined`, `my_donation_total`

Things to handle:
- **Money fields are strings** (e.g. `"175.00"`). `progress_percent` is a whole number from 0 to 100, or `null` when there's no goal. Use it for the progress bar.
- **Logged-in extras:** send the volunteer token (the shared axios client already does) and `has_joined` (true/false) and `my_donation_total` are filled in. Without a token, or with an expired one, they are `null` and the page still loads.
- **"Join this campaign" button:** show it when `allow_volunteers` is true, `status` isn't `completed` and the visitor is logged in. Use `has_joined` to switch the button to "Leave".

| Call (volunteer token) | Purpose |
|---|---|
| `POST /api/campaigns/{id}/join/` | Join. **201** the first time, **200** if already joined. **400** if the campaign isn't taking volunteers or has ended, **404** if it isn't published |
| `DELETE /api/campaigns/{id}/join/` | Leave |
| `GET /api/auth/me/campaigns/` *(paginated)* | Campaigns I joined, each with `joined_at` and `my_donation_total` |

Join and leave both return `{ "message", "has_joined", "volunteer_count" }`, so you can update the button and the count without reloading.

```js
const join = (id) => api.post(`/api/campaigns/${id}/join/`).then((r) => r.data);
const leave = (id) => api.delete(`/api/campaigns/${id}/join/`).then((r) => r.data);
```

### User search — `GET /api/website/users/?search=riy` (**token required**, volunteer or admin)
**200** `{ "count": 2, "returned": 2, "results": [ { "id", "name", "email", "volunteer_id" } ] }`

---

## 9. Contact form — `POST /api/contact/` (public)

Guest (all fields required):
```json
{ "name": "Amit", "contact": "9876543210", "email": "amit@example.com",
  "address": "Pune", "message": "I want to help." }
```
Logged-in volunteer (only `user` + `message`; use the volunteer's numeric `id`):
```json
{ "user": 5, "message": "I want to help." }
```
**201** `{ "message": "Message sent successfully." }` · **400** `{ "Error": "Message is required." }` / `"All fields are required."`

Take `user` from `user.id` in the login response, or from `GET /api/auth/me/`. Messages land in the admin panel inbox.

---

## 10. Local setup checklist for frontend devs

1. The backend `.env` must list your dev origin, otherwise the browser blocks requests with a CORS error:
   ```
   CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
   ALLOWED_HOSTS=127.0.0.1,localhost
   DEBUG=True
   ```
2. Frontend `.env`: `VITE_API_URL=http://127.0.0.1:8000`
3. Keep trailing slashes on URLs (`/api/auth/login/`). Without them Django returns 404 or tries to redirect.
4. Dates are ISO 8601 in IST (`+05:30`).
