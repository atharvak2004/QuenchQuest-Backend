# QuenchQuest – Admin Panel API Guide

This guide is for the admin panel app. The public website is covered in [FRONTEND_API_GUIDE.md](FRONTEND_API_GUIDE.md), which also explains error shapes, tokens and the axios refresh interceptor. Reuse that setup here.

- Log in with `POST /api/auth/sisuser/login/` and send `Authorization: Bearer <token>` on every call.
- Every write lives under **`/api/admin/`**. Public reads stay under `/api/website/`.
- Try any endpoint at `/api/docs/` (Swagger). Use **Authorize** and paste the token.
- Add the admin panel's origin to `CORS_ALLOWED_ORIGINS` in the backend `.env`, e.g. `http://localhost:5174`.

---

## 1. Roles and modules

| Role (`choice`) | Default modules |
|---|---|
| `admin` | everything: `content`, `inbox`, `volunteers`, `campaigns`, `staff` |
| `employee_role` | `content`, `inbox`, `volunteers`, `campaigns` |
| `editor` | `content` |

An admin can narrow an employee's or editor's access with `module_access`, e.g. `["content", "inbox"]`. The login response returns the user's effective `modules`, so show only those sections in the menu. Calling a module the user doesn't have returns **403**.

| Module | Endpoints |
|---|---|
| `content` | services, projects, leadership, impact, faqs, content-blocks, pages, media, settings |
| `inbox` | contacts |
| `volunteers` | volunteers, plus the volunteer actions on a project |
| `campaigns` | campaigns, beneficiaries, donations |
| `staff` | staff |
| any staff | dashboard, change own password |

---

## 2. Conventions (the same everywhere)

**Lists** are paginated as `{ count, next, previous, results }`. Query params:

| Param | Example | Notes |
|---|---|---|
| `page`, `page_size` | `?page=2&page_size=50` | default 20, max 100 |
| `search` | `?search=water` | searches the fields named in each section |
| `ordering` | `?ordering=-updated_at` | prefix `-` for descending |
| `archived` | `?archived=true` / `?archived=all` | content only; the default hides archived items |
| `is_published` | `?is_published=false` | content only; `false` lists drafts |

**Updates** use `PATCH` with only the changed fields. There is no `PUT`.

**Content items** all share these fields: `created_at`, `updated_at`, `updated_by`, `updated_by_name`, `is_archived`, `archived_at`. Most also have `is_published`; new items start as **drafts** (`is_published: false`).

**Delete is two-step** (soft delete):
1. The first `DELETE /{id}/` archives the item and takes it off the website: `{ "archived": true }`.
2. `POST /{id}/restore/` brings it back (still a draft).
3. A second `DELETE` on an archived item removes it permanently: `{ "archived": false }`.

**Shared actions on content** (which ones each resource has is listed in section 3):

| Action | Call | Notes |
|---|---|---|
| Publish / unpublish | `POST /{id}/publish/`, `POST /{id}/unpublish/` | Archived items can't be published (400) |
| Duplicate | `POST /{id}/duplicate/` | Creates a draft copy titled "… (copy)" with a new slug |
| Reorder | `POST /reorder/` with `{"ids": [3, 1, 2]}` | Send the full order after a drag-and-drop |
| Preview | `POST /{id}/preview/` | Returns `{ token, expires_in: 3600, api_url }` |
| Image | `POST /{id}/image/` (multipart) | See below |

**Preview:** open the website page with the token, e.g. `https://site/projects/{slug}?preview=<token>`. The website passes it to the API. The link works for one hour, including for drafts.

**Images:**
- Upload: `POST /{id}/image/` as `multipart/form-data` with `image` (a file), `alt` (required the first time) and optional `field` (`cover_image` by default, or `share_image` for SEO).
- Or reuse a media-library image: send JSON `{ "media_id": 12, "field": "cover_image" }`. Its alt text is copied unless you send `alt`.
- Remove: `DELETE /{id}/image/?field=cover_image`.
- Rules: JPEG, PNG or WebP only, up to **5 MB**. The backend keeps the original (`cover_image`) and makes a resized WebP of at most 1600 px (`cover_image_web`). All URLs come back absolute.

```js
const form = new FormData();
form.append("image", file);
form.append("alt", "Children at the Kolhapur learning centre");
await api.post(`/api/admin/services/${id}/image/`, form); // axios sets the multipart header
```

**Slugs** are generated from the title on create. To rename one, PATCH `slug`. The old slug keeps working on the website as a 301 redirect.

**List fields are JSON arrays.** Send them whole in the same PATCH body. For drag-to-reorder rows, change the array order and PATCH it.

**Errors:** `400` returns field errors such as `{ "activities": ["Must be a JSON array of strings."] }`. Show them next to the field.

---

## 3. Content (module `content`)

### Services — `/api/admin/services/`
Actions: publish, duplicate, reorder, image (`cover_image`, `share_image`), preview, restore.
Filters: `?is_published=`, `?show_on_home=`, `?search=` (title and descriptions).

```json
{
  "title": "Education & Child Welfare",
  "slug": "education-child-welfare",
  "short_description": "max 160 chars, shown on the home card",
  "description": "Long text for /programs",
  "icon": "book",
  "cover_image_alt": "…",
  "home_layout": "wide",
  "activities_heading": "Key Activities",
  "activities": ["Tutoring", "Books, bags and uniforms"],
  "beneficiaries_heading": "Target Beneficiaries",
  "beneficiaries": ["Children aged 6-14"],
  "display_order": 1,
  "is_published": false,
  "show_on_home": true,
  "seo_title": "", "seo_description": ""
}
```
`icon` is one of `book, heart, chart, shield, health, sprout, leaf, users`. `home_layout` is `wide` or `tall`.

### Projects — `/api/admin/projects/`
Actions: publish, duplicate (also copies the gallery), reorder, image, preview, restore, plus:

| Call | Purpose |
|---|---|
| `GET /api/admin/projects/template/` | Default `phases` (Discover, Deliver, Review) and `safeguards` |
| `POST /api/admin/projects/?template=default` | Create, filling in the defaults when `phases` / `safeguards` are empty |
| `POST /api/admin/projects/featured-order/` | `{"ids": [5, 2, 9]}` sets the home cards in order (max 3); unfeatures the others |
| `POST /api/admin/projects/{id}/gallery/` | Multipart `image` + `alt` (or `media_id`) adds a photo; returns `{ id, image, image_web, alt }` |
| `DELETE /api/admin/projects/{id}/gallery/{image_id}/` | Remove a gallery photo |
| `GET` / `POST` / `DELETE /api/admin/projects/{id}/volunteers/` | List, add or remove volunteers: `{"volunteer_ids": [4, 7]}`. Needs the `volunteers` module |
| `GET /api/admin/projects/{id}/suggested-volunteers/?skills=teaching,design` | Verified, active volunteers matching the skills or the project's city, best first |

Filters: `?service=<id>`, `?status=`, `?is_featured=`, `?is_published=`, `?search=` (title, summary, location).

```json
{
  "title": "Clean Water for Kolhapur",
  "service": 3,
  "status": "active",
  "summary": "max 200 chars",
  "cover_image_alt": "…",
  "location_name": "Kolhapur, Maharashtra",
  "latitude": "16.705000", "longitude": "74.243300",
  "show_on_map": true,
  "challenge": "…", "objective": "…", "participants": "…",
  "activities": ["Install filters", "Train local caretakers"],
  "phases": [{ "name": "Discover", "description": "…" }],
  "indicators": [{ "area": "Health", "measurement_method": "Household survey", "evidence_source": "Clinic records" }],
  "safeguards": ["Informed consent before any photo is taken."],
  "people_benefited": 420,
  "people_benefited_verified": false,
  "start_date": "2026-06-01", "end_date": null,
  "is_featured": false, "featured_order": 0,
  "is_published": false
}
```
The response also includes `service_title`, `gallery`, `volunteer_count` and the audit fields.

Validation:
- Only **3** projects can be featured at once.
- `end_date` can't be before `start_date`.
- `latitude` must be between -90 and 90, `longitude` between -180 and 180.
- Every phase needs a `name`, and every indicator needs an `area`.

The website shows `people_benefited` only when `people_benefited_verified` is `true`.

**Map picker:** the backend stores only `latitude`, `longitude` and `location_name`. Do the place search and map clicks in the panel, e.g. with Leaflet and OpenStreetMap Nominatim.

### Impact numbers — `/api/admin/impact/`
`{ "children_women_supported": 1200, "skill_awareness_programs": 35, "communities_reached": 18, "date": "2026-11-01", "is_published": true }`
The website shows the newest published record by `date`. Actions: publish, restore.

### Leadership — `/api/admin/leadership/`
`{ "name", "position", "short_description", "display_order", "is_published" }`. The photo goes through `POST /{id}/image/` (field `image`, with `alt`). Actions: publish, reorder, image, restore. Existing records stay published.

### FAQs — `/api/admin/faqs/`
`{ "question", "answer", "display_order", "is_published" }`. Actions: publish, reorder, restore.

### Site settings — `GET` / `PATCH /api/admin/settings/`
There is a single record, so there's no id:
```json
{
  "contact_email": "", "contact_phone": "", "address": "",
  "linkedin_url": "", "instagram_url": "", "facebook_url": "", "youtube_url": "",
  "footer_tagline": "",
  "get_involved_options": [{ "title": "Corporate partnership", "description": "…" }],
  "donate_focus_areas": [{ "title": "Education", "description": "…" }]
}
```

### Content blocks — `/api/admin/content-blocks/`
Keyed text for the About page, home hero and so on. `key` uses lowercase letters, digits, `.`, `-` and `_`.
`{ "key": "about.vision", "title": "", "body": "…", "data": {}, "is_published": true }`
Put structured content in `data`, e.g. `{"items": ["Objective 1", "…"]}` for the four core objectives. A block can hold one image (field `image`) via `/image/`. Filter with `?prefix=about.`.

Suggested keys: `about.vision`, `about.mission`, `about.objectives`, `home.hero.headline`, `home.hero.subtext`, `home.hero.photo1`, `home.hero.photo2`.

### Pages — `/api/admin/pages/`
For legal pages: `{ "title": "Privacy Policy", "body": "<p>HTML…</p>", "seo_title", "seo_description", "is_published" }`. Use a rich-text editor that outputs HTML (TipTap, Quill). Actions: publish, duplicate, image (`share_image`), preview, restore.

### Media library — `/api/admin/media/`
- `POST` multipart: `file` and `alt` (both required), optional `title`. Returns `{ id, file, file_web, alt, title, width, height, size_bytes, uploaded_by_name, created_at }`.
- `PATCH` changes `alt` / `title`. The file itself can't be replaced.
- `DELETE` removes the library entry; items already using the image keep it.
- Search with `?search=` on title and alt.
- Use the `id` as `media_id` in any image or gallery call.

---

## 4. Inbox (module `inbox`) — `/api/admin/contacts/`

| Call | Purpose |
|---|---|
| `GET /api/admin/contacts/?status=new&assigned_to=me` | List. `status` is `new`, `in_progress`, `replied` or `closed`. `assigned_to` is `<id>`, `me` or `none`. `search` covers name, email and message |
| `GET /api/admin/contacts/{id}/` | One message, with its notes |
| `PATCH /api/admin/contacts/{id}/` | `{ "status": "replied" }` and/or `{ "assigned_to": 4 }` (or `null`) |
| `POST /api/admin/contacts/{id}/notes/` | `{ "text": "Called back, will visit Monday" }`. Internal only; moves a `new` message to `in_progress` |
| `GET /api/admin/contacts/export/` | CSV download. Takes the same filters as the list |

Each message has `sender_name`, `sender_email` and `sender_phone` for both registered and guest senders, and `is_registered` tells them apart. The message text can't be edited. Messages can only be assigned to staff who have the inbox module.

**Downloading CSV files:** request with `responseType: "blob"` so the auth header is sent:
```js
const res = await api.get("/api/admin/contacts/export/", { params: filters, responseType: "blob" });
const url = URL.createObjectURL(res.data);
Object.assign(document.createElement("a"), { href: url, download: "messages.csv" }).click();
URL.revokeObjectURL(url);
```

---

## 5. Volunteers (module `volunteers`) — `/api/admin/volunteers/`

| Call | Purpose |
|---|---|
| `GET /api/admin/volunteers/` | Filters: `?skills=`, `?location=`, `?availability=` (all "contains"), `?gender=`, `?is_verified=`, `?is_active=`, `?project=<id>`, plus `search` and `ordering` |
| `GET` / `PATCH /api/admin/volunteers/{id}/` | `{ name, email, phone, gender, skills, location, availability, is_verified, is_active }` |
| `DELETE /api/admin/volunteers/{id}/` | **Deactivates** the volunteer: they can't log in, and their tokens stop working |
| `POST /api/admin/volunteers/{id}/activate/` | Undo a deactivation |
| `POST /api/admin/volunteers/{id}/resend-verification/` | Emails a new OTP (400 if already verified) |
| `GET /api/admin/volunteers/export/` | CSV download with the same filters |

To create a volunteer, keep using `POST /api/dashboard/volunteers/`; it returns the generated password. For matching volunteers to a project, see the Projects section.

---

## 6. Staff accounts (module `staff`, admins only) — `/api/admin/staff/`

| Call | Purpose |
|---|---|
| `GET /api/admin/staff/?role=editor&is_active=true` | List |
| `POST /api/admin/staff/` | `{ username, email, phone, location, choice, module_access, password }`. `password` needs at least 8 characters |
| `PATCH /api/admin/staff/{id}/` | Change details, role or `module_access`. You can't remove your own admin role |
| `DELETE /api/admin/staff/{id}/` | Deactivate (not your own account) |
| `POST /api/admin/staff/{id}/activate/` | Reactivate |
| `POST /api/admin/staff/{id}/reset-password/` | `{ "new_password": "…" }`. Logs that person out everywhere and unlocks the account |
| `POST /api/admin/staff/{id}/unlock/` | Clear a lockout (5 wrong passwords lock the account for 15 minutes) |

Each staff member returns `modules`, `last_login`, `locked_until` and `failed_login_attempts`. Use them to show status badges.

Users change their own password with `POST /api/auth/sisuser/change-password/` (see the website guide).

---

## 7. Campaigns, beneficiaries, donations (module `campaigns`)

### Campaigns — `/api/admin/campaigns/`
Campaigns work like services: new ones start as drafts, deleting archives first, and edits are audited.
Actions: publish, duplicate, reorder, image (`cover_image`, `share_image`), preview, restore.
Filters: `?status=`, `?is_featured=`, `?service=<id>`, `?is_published=`, `?archived=`, `?search=` (title, summary, description, location).

```json
{
  "title": "Clean Water Drive",
  "slug": "clean-water-drive",
  "summary": "max 200 chars, card text",
  "description": "Full campaign page",
  "cover_image_alt": "…",
  "status": "active",
  "start_date": "2026-12-01", "end_date": "2027-01-31",
  "goal_amount": "50000.00",
  "service": 3,
  "project": 7,
  "location_name": "Pune, Maharashtra",
  "allow_volunteers": true,
  "is_featured": true, "display_order": 1,
  "is_published": false,
  "seo_title": "", "seo_description": ""
}
```
- `status` is `upcoming` (the default), `active` or `completed`. It replaces the old `is_active` flag.
- The response also includes these read-only fields:
  - `raised_amount` (the sum of donations linked to the campaign)
  - `donor_count` (distinct donors)
  - `volunteer_count` (volunteers who joined)
  - `progress_percent` (`raised_amount` as a share of `goal_amount`, capped at 100; `null` when there's no goal)
  - `service_title`, `project_title`, `project_slug`, plus the audit fields
- `end_date` can't be before `start_date`, and `goal_amount` can't be negative.
- `allow_volunteers` controls whether the website shows "Join this campaign". Volunteers can't join `completed` campaigns either way.

| Call | Purpose |
|---|---|
| `GET /api/admin/campaigns/{id}/volunteers/` | Who joined (paginated): `{ id, volunteer_id, name, email, phone, skills, location, joined_at }` |
| `GET /api/admin/campaigns/{id}/volunteers/export/` | The same list as CSV |

Existing campaigns were migrated: each got a slug from its title, `active` ones kept `status: active` and the rest became `completed`, and all stay published.

### Donations — `/api/admin/donations/`
`{ donor, amount, campaign }`. `donor` (a volunteer id) is required; `campaign` is optional and counts the donation towards that campaign's `raised_amount`. Each donation returns `campaign_title`.
Filters: `?campaign=<id>`, `?campaign=none` (not linked to a campaign), `?donor=<id>`.

### Beneficiaries — `/api/admin/beneficiaries/`
`{ user, age, need, location, status }`. Filter with `?status=pending|approved|helped`.

Donations and beneficiaries are deleted permanently, with no archive step.

---

## 8. Dashboard home (any staff) — `GET /api/admin/dashboard/`

```json
{
  "volunteers": { "total": 120, "new_this_week": 6, "unverified": 9, "inactive": 1 },
  "messages":   { "unread": 3, "open": 5, "assigned_to_me": 2 },
  "content":    { "published_projects": 6, "draft_projects": 1, "published_services": 8, "draft_services": 0,
                  "published_campaigns": 4, "active_campaigns": 2 },
  "recent_activity": [
    { "type": "message_received", "id": 41, "text": "New message from Amit", "at": "2026-11-18T10:02:00+05:30" },
    { "type": "content_updated", "model": "project", "id": 3, "text": "admin updated project \"Clean Water\"", "at": "…" },
    { "type": "volunteer_registered", "id": 120, "text": "Riya Patil registered", "at": "…" }
  ]
}
```
`recent_activity` holds the latest 15 events, newest first. Link each one to `/{model}/{id}`, `/inbox/{id}` or `/volunteers/{id}`.

---

## 9. Not built yet (Phase 3)

These wait for the gates in the spec: audit log and version restore, scheduled publishing, online donations (Razorpay, 80G receipts), emailing volunteers about matching projects, and two-factor login for admins.
