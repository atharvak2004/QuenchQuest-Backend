# Deploying QuenchQuest (API + website) on the EC2 server

This runbook puts the **backend** (this repo) and the **website** (`quenchquest-homepage`) on the
existing EC2 server, pulled from GitHub with deploy keys. It first removes the **old QuenchQuest
project** from the server. Phase 1 runs on the server's **IP address**; the domain is connected
later (step 12).

| | Address in phase 1 | Runs as |
|---|---|---|
| Website | `http://<SERVER-IP>:8080` | `qqweb`, Next.js on `127.0.0.1:3100` |
| API | `http://<SERVER-IP>:8081` | `qqapi`, gunicorn on a Unix socket |

Replace `<SERVER-IP>` everywhere with the instance's public (Elastic) IP, and `<GITHUB-OWNER>`
with your GitHub user or organisation.

---

## 0. Kavya must not be disturbed — rules for every step

Kavya is live on this server. Everything below is written so that **nothing of Kavya's is stopped,
restarted or changed**. Keep to these rules:

| Never do this | Why | Do this instead |
|---|---|---|
| Stop, reboot or resize the EC2 instance | Kavya goes down | Nothing here needs it |
| `sudo systemctl restart nginx` / `stop nginx` | Drops every site's connections, Kavya's included | `sudo nginx -t && sudo systemctl reload nginx` (see below) |
| `sudo apt upgrade` / `apt full-upgrade` | Can upgrade libraries and auto-restart Kavya's services | Install only the named packages, with `NEEDRESTART_MODE=l` |
| Install Node from NodeSource (`apt install nodejs`) | Replaces the system Node that Kavya may run on | Private Node 22 in `/opt/node22` (step 5.3) |
| `pm2 restart all`, `pm2 kill`, `pm2 update`, `pm2 delete all` | Restarts or removes Kavya if it runs under PM2 | Only ever name the old QuenchQuest process |
| `sudo rm /etc/nginx/sites-enabled/default` (the website guide says to) | Kavya may be the default site | Leave it. Our config uses its own ports |
| Edit or remove any nginx file, service, cron job or folder you haven't confirmed is QuenchQuest's | It might be Kavya's | Check with step 2 first. If unsure, ask before touching it |
| Restart MySQL | Kavya may share it | Not needed: users and databases are created live |

**About `nginx reload`:** removing the old site and adding the new one each need one Nginx
reload. A reload is **graceful**. Nginx starts new workers with the new config, and the old
workers finish every request they are serving before they exit. No connection is dropped, and
Kavya keeps answering throughout. A *restart* is what takes sites down, and this guide never
uses one. Always run `sudo nginx -t` first; if it reports an error, **don't reload**. Nginx then
keeps running the old, working config.

Before and after each reload, check that Kavya still answers:

```bash
curl -s -o /dev/null -w "Kavya: %{http_code}\n" https://<KAVYA-DOMAIN>/
```

**Build load:** building the website takes CPU and memory. The update script runs it in a capped systemd scope (hard RAM limit, CPU cap, lowest I/O weight), so it can only swap out its own memory, never Kavya's. It also runs it at the
lowest priority (`nice`/`ionice`) with a memory cap, and refuses to start when memory is short.
Add swap first (step 5.2).

---

## 1. Put both projects on GitHub (your PC)

**Backend** (this repo, already a git repository):

```bash
cd E:/PrushalTech-Backend/quenchQuestBackend
git status          # .env / project/.env must NOT be listed (they're in .gitignore)
git add -A
git commit -m "Admin panel, volunteering, certificates, deployment files"
git remote -v       # add one if empty: git remote add origin git@github.com:<GITHUB-OWNER>/quenchQuestBackend.git
git push -u origin main
```

**Website** (`E:/PrushalTech/quenchquest-homepage` is **not** a git repository yet):

```bash
cd E:/PrushalTech/quenchquest-homepage
git init -b main
git status          # .env.local must NOT be listed (.gitignore has .env*)
git add -A
git commit -m "QuenchQuest website"
git remote add origin git@github.com:<GITHUB-OWNER>/quenchquest-homepage.git
git push -u origin main
```

Create both repositories on GitHub first, and keep them **private**.

---

## 2. Look at the server first (read-only)

Connect: `ssh -i <your-key.pem> ubuntu@<SERVER-IP>`.

Everything in this block only **reads**; it changes nothing. Run it and save the output.
**Send it to me (Claude) before step 4.** Then the removal commands can name the old
project's exact files and services, with nothing of Kavya's in them.

```bash
echo "=== system";   uname -m; lsb_release -ds; nproc; free -h; swapon --show; df -h /
echo "=== versions"; which node && node -v; which python3 && python3 --version; nginx -v 2>&1; mysql --version 2>/dev/null
echo "=== ports in use";  sudo ss -tlnp
echo "=== running services (non-system)"
systemctl list-units --type=service --state=running --no-pager | grep -v -E "systemd|snap|cron|ssh|dbus|getty|polkit|rsyslog|udev|multipathd|networkd|resolved|chrony|unattended|ModemManager|packagekit|irqbalance|accounts-daemon|udisks|amazon-ssm|cloud"
echo "=== custom unit files";  ls -l /etc/systemd/system/*.service /etc/systemd/system/*.socket 2>/dev/null
echo "=== pm2 (ubuntu)";       command -v pm2 && pm2 ls
echo "=== pm2 (root)";         sudo bash -lc 'command -v pm2 && pm2 ls'
echo "=== nginx sites";        ls -l /etc/nginx/sites-enabled/ /etc/nginx/conf.d/
echo "=== nginx routing";      sudo nginx -T 2>/dev/null | grep -n -E "^# configuration file|server_name|listen|root |alias |proxy_pass|upstream|ssl_certificate "
echo "=== QuenchQuest files";  sudo find / -xdev -iname "*quench*" -not -path "/proc/*" -not -path "*/node_modules/*" 2>/dev/null | head -60
echo "=== .env files";         sudo find /var/www /home /srv /opt -maxdepth 4 -name ".env" 2>/dev/null
echo "=== cron";               crontab -l 2>/dev/null; sudo crontab -l 2>/dev/null; ls /etc/cron.d
echo "=== mysql databases";    sudo mysql -e "SHOW DATABASES;" 2>/dev/null || echo "(no local MySQL root access — may be RDS or needs a password)"
echo "=== certbot";            sudo certbot certificates 2>/dev/null | grep -E "Certificate Name|Domains"
```

From this we'll know:
- which service, PM2 process, nginx file and folder belong to the old QuenchQuest
- which belong to **Kavya**
- whether the ports 3100, 8080 and 8081 are free
- where the old database lives
- how much memory the build can use

---

## 3. Back up the old QuenchQuest project

Use the paths from step 2. `<OLD-DIR>` is the old project's folder, for example `/var/www/quenchQuestBackend`.

**3.1 The old `.env`.** Show it, and copy it to your PC:

```bash
sudo cat <OLD-DIR>/.env            # or <OLD-DIR>/project/.env — step 2 lists every .env
```

To download it as a file (on the server, then on your PC):

```bash
sudo cp <OLD-DIR>/.env ~/old-quenchquest.env && sudo chown ubuntu: ~/old-quenchquest.env && chmod 600 ~/old-quenchquest.env
```

```bash
scp -i <your-key.pem> ubuntu@<SERVER-IP>:~/old-quenchquest.env ./old-quenchquest.env
```

Keep it somewhere safe. It holds the database password and the Gmail app password, so never
commit it. Afterwards, delete the server copy: `rm ~/old-quenchquest.env`.

**3.2 The database.** `--single-transaction` takes a consistent copy **without locking tables**,
so Kavya isn't slowed or blocked even if it uses the same MySQL. Take `DB_HOST`, `DB_USER` and
`DB_NAME` from the old `.env`:

```bash
mkdir -p ~/backups
mysqldump --single-transaction --quick --routines --triggers \
  -h <DB_HOST> -u <DB_USER> -p <DB_NAME> | gzip > ~/backups/quenchquest-db-$(date +%F).sql.gz
ls -lh ~/backups/
```

**3.3 Uploaded files** (if the old project has a `media/` folder):

```bash
sudo tar -czf ~/backups/quenchquest-media-$(date +%F).tar.gz -C <OLD-DIR> media
```

Download both backups to your PC as well, with `scp`, before removing anything.

---

## 4. Remove the old QuenchQuest project

> Fill in the names from step 2 and check each one is QuenchQuest's, not Kavya's.
> `systemctl cat <unit>` shows a service's folder. If one file or service mixes both projects,
> **stop and ask**; don't delete it.

```bash
# 4.1 Stop the old app — use ONLY the line that matches how it runs
sudo systemctl disable --now <old-quenchquest>.service          # systemd (also its .socket, if any)
pm2 delete <old-quenchquest-name> && pm2 save                    # PM2 — as the user that owns it

# 4.2 Take its nginx site out — this file only
sudo rm /etc/nginx/sites-enabled/<old-quenchquest-site>
sudo nginx -t && sudo systemctl reload nginx                     # graceful; check Kavya with curl

# 4.3 Move its unit file and folder aside (delete for good in a week if nothing missed it)
mkdir -p ~/old-quenchquest-removed
sudo mv /etc/systemd/system/<old-quenchquest>.service ~/old-quenchquest-removed/ 2>/dev/null
sudo systemctl daemon-reload                                     # re-reads unit files; restarts nothing
sudo mv <OLD-DIR> ~/old-quenchquest-removed/

# 4.4 Remove its cron lines, if any (crontab -e / sudo crontab -e)
```

Things to keep:
- **The database.** Keep it for now; the new API can start from a copy of it (step 7.2).
- **The SSL certificate.** Certbot reuses it when the domain is connected (step 12).
- **DNS.** If the QuenchQuest domain points at this server, then once the old site is removed,
  visitors to that domain may land on the server's default site, which could be Kavya. Tell me
  if the domain points here, and I'll give you a two-line "parked" config for it until step 12.

---

## 5. One-time server setup

### 5.1 Packages (only these, no upgrade)

```bash
sudo apt-get update                                   # refreshes the package list only
sudo NEEDRESTART_MODE=l apt-get install -y \
  git curl python3-venv python3-dev build-essential pkg-config default-libmysqlclient-dev
nginx -v || sudo NEEDRESTART_MODE=l apt-get install -y nginx    # only if Nginx isn't installed yet
```

`NEEDRESTART_MODE=l` makes Ubuntu only *list* services that could use a restart, instead of
restarting them.

### 5.2 Swap (skip if `swapon --show` already shows one)

Adding swap doesn't restart anything. It lets the website build run without squeezing Kavya.

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

### 5.3 Private Node 22 (the system Node stays as it is)

```bash
cd /tmp
BASE=https://nodejs.org/dist/latest-v22.x
ARCH=$(uname -m | sed 's/aarch64/arm64/; s/x86_64/x64/')       # this server is ARM (Graviton): arm64
TAR=$(curl -fsSL $BASE/SHASUMS256.txt | awk -v f="linux-$ARCH.tar.xz" '$2 ~ f"$" {print $2}')
curl -fsSLO "$BASE/$TAR"
curl -fsSL $BASE/SHASUMS256.txt | grep " $TAR\$" | sha256sum -c -     # must print: OK
sudo mkdir -p /opt/node22 && sudo tar -xJf "$TAR" -C /opt/node22 --strip-components=1
/opt/node22/bin/node -v        # v22.x
rm "$TAR"
```

### 5.4 Users and folders

```bash
sudo useradd --system --home /var/www/quenchquest-web --shell /usr/sbin/nologin qqweb
sudo useradd --system --no-create-home --shell /usr/sbin/nologin qqapi

sudo mkdir -p /var/www/quenchquest-web/releases /var/www/quenchquest-api /var/www/quenchquest-web-src
sudo chown -R qqweb:qqweb /var/www/quenchquest-web
sudo chown ubuntu:ubuntu /var/www/quenchquest-api /var/www/quenchquest-web-src

# Uploaded media + collected static files: written by qqapi, readable by Nginx (www-data)
sudo mkdir -p /var/lib/quenchquest-api/media /var/lib/quenchquest-api/static
sudo chown -R qqapi:www-data /var/lib/quenchquest-api
sudo chmod -R 2750 /var/lib/quenchquest-api
```

### 5.5 GitHub deploy keys (one per repository, read-only)

GitHub allows a deploy key on only one repository, so make two. Each key can read just its own repo.

```bash
ssh-keygen -t ed25519 -N "" -C "quenchquest-api@ec2" -f ~/.ssh/qq_api_deploy
ssh-keygen -t ed25519 -N "" -C "quenchquest-web@ec2" -f ~/.ssh/qq_web_deploy

# Add host aliases (>> appends; it never overwrites an existing ~/.ssh/config)
cat >> ~/.ssh/config <<'EOF'

Host github-qq-api
    HostName github.com
    User git
    IdentityFile ~/.ssh/qq_api_deploy
    IdentitiesOnly yes

Host github-qq-web
    HostName github.com
    User git
    IdentityFile ~/.ssh/qq_web_deploy
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

cat ~/.ssh/qq_api_deploy.pub     # → backend repo
cat ~/.ssh/qq_web_deploy.pub     # → website repo
```

On GitHub, for **each** repository: **Settings → Deploy keys → Add deploy key**. Paste the
matching `.pub` line, give it a title such as `EC2`, and leave **"Allow write access" off**.

Test both:

```bash
ssh -T github-qq-api      # "Hi <GITHUB-OWNER>/quenchQuestBackend! You've successfully authenticated…"
ssh -T github-qq-web
```

---

## 6. Clone both repositories

```bash
git clone github-qq-api:<GITHUB-OWNER>/quenchQuestBackend.git /var/www/quenchquest-api
git clone github-qq-web:<GITHUB-OWNER>/quenchquest-homepage.git /var/www/quenchquest-web-src
```

---

## 7. Backend (API)

### 7.1 Python environment

```bash
cd /var/www/quenchquest-api
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### 7.2 Database

Use a **new** database restored from the old backup. This keeps the volunteers, messages and
content, and leaves the old database untouched as a fallback.

If MySQL runs on this server, step 2 showed the databases. Use `sudo mysql` if root signs in
that way, otherwise `mysql -u root -p`. For RDS, use `-h <DB_HOST> -u <admin user> -p`.

```bash
DBPASS=$(openssl rand -hex 16); echo "Save this DB password: $DBPASS"
sudo mysql <<SQL
CREATE DATABASE quenchquest_v2 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'qq_app'@'localhost' IDENTIFIED BY '$DBPASS';
GRANT ALL PRIVILEGES ON quenchquest_v2.* TO 'qq_app'@'localhost';
SQL
gunzip < ~/backups/quenchquest-db-<DATE>.sql.gz | sudo mysql quenchquest_v2
```

Creating a database and a user is done live; MySQL keeps serving Kavya.

To start with an **empty** database instead, skip the `gunzip` line.

### 7.3 Settings: `/var/www/quenchquest-api/.env`

Generate two secrets:

```bash
openssl rand -hex 32     # → SECRET_KEY
openssl rand -hex 32     # → WEBSITE_REVALIDATE_SECRET (also goes in the website settings, step 8.2)
```

```bash
sudo touch /var/www/quenchquest-api/.env
sudo chown qqapi:qqapi /var/www/quenchquest-api/.env && sudo chmod 600 /var/www/quenchquest-api/.env   # only the API user can read it
sudo nano /var/www/quenchquest-api/.env
```

```ini
SECRET_KEY=<first openssl value>
DEBUG=False

ALLOWED_HOSTS=<SERVER-IP>,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://<SERVER-IP>:8080,http://<SERVER-IP>:8081
CORS_ALLOWED_ORIGINS=http://<SERVER-IP>:8080

ENGINE=django.db.backends.mysql
DB_NAME=quenchquest_v2
DB_USER=qq_app
DB_PASSWORD=<DBPASS from 7.2>
DB_HOST=localhost
DB_PORT=3306

# From the old .env (and rotate this Gmail app password — the old one was in git history)
EMAIL_HOST_USER=quenchquestsocialfoundation@gmail.com
EMAIL_HOST_PASSWORD=<gmail app password>
ADMIN_NOTIFICATION_EMAIL=quenchquestsocialfoundation@gmail.com

# Files
MEDIA_ROOT=/var/lib/quenchquest-api/media
STATIC_ROOT=/var/lib/quenchquest-api/static
MEDIA_URL=http://<SERVER-IP>:8081/media/

# Website refresh hook (the website runs on 127.0.0.1:3100)
WEBSITE_REVALIDATE_URL=http://127.0.0.1:3100/api/revalidate
WEBSITE_REVALIDATE_SECRET=<second openssl value>

# Certificates: the QR code opens this page
CERTIFICATE_VERIFY_URL=http://<SERVER-IP>:8080/verify

# Google sign-in needs HTTPS on a real domain — leave empty until step 12
GOOGLE_CLIENT_ID=
```

On Linux, install a serif font for the certificates (it restarts nothing):
`sudo NEEDRESTART_MODE=l apt-get install -y fonts-dejavu-core`.

### 7.4 Migrate, collect static files, create the admin

```bash
cd /var/www/quenchquest-api
sudo -u qqapi .venv/bin/python manage.py check
sudo -u qqapi .venv/bin/python manage.py migrate
sudo -u qqapi .venv/bin/python manage.py collectstatic --noinput
```

If the old database had uploaded images, restore them into the new media folder:

```bash
sudo tar -xzf ~/backups/quenchquest-media-<DATE>.tar.gz -C /var/lib/quenchquest-api/ \
  && sudo chown -R qqapi:www-data /var/lib/quenchquest-api/media
```

Create the first admin. It asks for the password; nothing is shown or saved in your shell history:

```bash
sudo -u qqapi .venv/bin/python manage.py shell -c "import getpass; from authentication.models import SisUser; u = SisUser(username='admin', email='admin@quenchquest.local', choice='admin', is_staff=True, is_superuser=True); u.set_password(getpass.getpass('Password: ')); u.save(); print('Created', u.username)"
```

> **Two separate kinds of login.**
> - The admin panel (`/admin` on the website) signs in **staff accounts**: admins, employees and editors.
> - Django's built-in admin (`/admin/` on the API) signs in **Django's own user accounts**.
>
> `manage.py changepassword` only changes the **Django** accounts. To reset an **admin panel** password on the server, use this instead. It also clears a lock caused by too many wrong passwords:
>
> ```bash
> sudo -u qqapi .venv/bin/python manage.py shell -c "import getpass; from authentication.models import SisUser; u = SisUser.objects.get(username='admin'); u.set_password(getpass.getpass('New password: ')); u.failed_login_attempts = 0; u.locked_until = None; u.save(); print('Password set for', u.username)"
> ```
>
> Staff can also be given new passwords from **Staff → Reset password** inside the panel.

### 7.5 Service

```bash
sudo cp /var/www/quenchquest-api/deploy/quenchquest-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now quenchquest-api
systemctl status quenchquest-api --no-pager       # active (running)
```

---

## 8. Website

### 8.1 Build settings: `/var/www/quenchquest-web-src/.env.production`

```bash
nano /var/www/quenchquest-web-src/.env.production
```

```ini
NEXT_PUBLIC_API_URL=http://<SERVER-IP>:8081
NEXT_PUBLIC_SITE_URL=http://<SERVER-IP>:8080
NEXT_PUBLIC_GOOGLE_CLIENT_ID=
API_URL=http://127.0.0.1:8081
```

### 8.2 Runtime settings: `/etc/quenchquest-web.env`

```bash
sudo nano /etc/quenchquest-web.env && sudo chmod 600 /etc/quenchquest-web.env
```

```ini
API_URL=http://127.0.0.1:8081
REVALIDATE_SECRET=<same as the API's WEBSITE_REVALIDATE_SECRET>
PORT=3100
HOSTNAME=127.0.0.1
```

### 8.3 Service and deploy tool

The website repo's service file uses `/usr/bin/node`. This copy points it at the private Node 22 instead:

```bash
cd /var/www/quenchquest-web-src
sed 's#/usr/bin/node#/opt/node22/bin/node#' deploy/quenchquest-web.service \
  | sudo tee /etc/systemd/system/quenchquest-web.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable quenchquest-web             # starts with the first deploy

# Memory limit so the website can never take memory from other apps on the server
sudo mkdir -p /etc/systemd/system/quenchquest-web.service.d
printf '[Service]\nMemoryHigh=350M\nMemoryMax=500M\n' | sudo tee /etc/systemd/system/quenchquest-web.service.d/memory.conf > /dev/null
sudo systemctl daemon-reload

sudo cp deploy/deploy-release.sh /usr/local/bin/qq-deploy && sudo chmod +x /usr/local/bin/qq-deploy
```

---

## 9. Nginx for the IP address

The config listens on **8080** (website) and **8081** (API) with its own upstream names, so
it can't change how Kavya's sites are routed. First confirm both ports are free. This must print
nothing:

```bash
sudo ss -tlnp | grep -E ":(8080|8081|3100)\b"
```

```bash
sudo cp /var/www/quenchquest-api/deploy/nginx-quenchquest-ip.conf /etc/nginx/sites-available/quenchquest-ip
sudo ln -s /etc/nginx/sites-available/quenchquest-ip /etc/nginx/sites-enabled/quenchquest-ip
sudo nginx -t                                     # must say "syntax is ok" and "test is successful"
sudo systemctl reload nginx                       # graceful — check Kavya with curl after
curl -s -o /dev/null -w "API: %{http_code}\n" http://127.0.0.1:8081/api/website/settings/   # 200
```

**AWS security group** (EC2 console → the instance → Security → the group → Edit inbound rules):
add **Custom TCP 8080** and **Custom TCP 8081**, source `0.0.0.0/0`, or just your own IP while
testing. Adding rules doesn't affect existing connections or Kavya's rules.

---

## 10. First website deploy

```bash
bash /var/www/quenchquest-api/deploy/deploy-web.sh
```

It pulls, builds at low priority, unpacks and starts the site on 3100, health-checks it, and
rolls back automatically if the site doesn't answer. The first build takes a few minutes.

---

## 11. Check everything

```bash
systemctl status quenchquest-api quenchquest-web --no-pager
curl -s -o /dev/null -w "website %{http_code}\n" http://<SERVER-IP>:8080/
curl -s -o /dev/null -w "api %{http_code}\n"     http://<SERVER-IP>:8081/api/website/settings/
curl -s -o /dev/null -w "Kavya %{http_code}\n"   https://<KAVYA-DOMAIN>/          # unchanged
```

In the browser:
- `http://<SERVER-IP>:8080` shows the site, with content from the API.
- `http://<SERVER-IP>:8080/admin` lets you log in with the admin from 7.4.
- `http://<SERVER-IP>:8081/api/docs/` opens Swagger.
- After you save something in the admin panel, the public page updates within seconds (the refresh hook).

**Expected in the IP phase** (plain HTTP, no domain):
- Google sign-in is off. Google requires HTTPS on a real domain.
- The browser won't share the volunteer's location when they mark attendance by photo. The photo itself still works.
- Logins travel unencrypted. Keep the IP link to the team until HTTPS is on.

### Updating later

```bash
bash /var/www/quenchquest-api/deploy/deploy-api.sh    # backend: pull, migrate, graceful reload
bash /var/www/quenchquest-api/deploy/deploy-web.sh    # website: pull, build, deploy (auto-rollback)
sudo qq-deploy --rollback                             # website: back to the previous release
```

Logs: `journalctl -u quenchquest-api -f` and `journalctl -u quenchquest-web -f`.

---

## 12. Connect the domain and HTTPS (no downtime)

> **The domain is on Cloudflare (proxied, orange cloud).** Use **`deploy/nginx-quenchquest-cloudflare.conf`**
> instead of the certbot config described below. HTTPS between Cloudflare and the server then uses a
> free Cloudflare **origin certificate**: no certbot, and no renewals for 15 years.
> 1. In Cloudflare, open **SSL/TLS → Origin Server → Create Certificate**, for
>    `quenchquestsocialfoundation.org` and `*.quenchquestsocialfoundation.org`. Save the certificate as
>    `/etc/ssl/quenchquest/origin.pem` and the key as `/etc/ssl/quenchquest/origin.key` (mode 600).
> 2. Enable the config next to the IP one, then `nginx -t` and reload. Port 80 and 443 both serve the
>    site, so it works under "Flexible" and "Full (strict)".
> 3. In Cloudflare, set **SSL/TLS mode → Full (strict)** and turn on **Always Use HTTPS**, for this domain only.
> 4. Continue with steps 4–6 below (API `.env`, website rebuild, IP setup off).

The domain config runs **alongside** the IP config, so the IP address keeps working until the
domain is fully ready.

1. **DNS.** `quenchquestsocialfoundation.org`, `www` and `api` must all point at `<SERVER-IP>`.
   Check with `getent hosts <name>`. Certbot fails if any of the three points elsewhere.
2. **Enable the domain config** next to the IP one. It uses its own upstream names, so both can be on:
   ```bash
   cd /var/www/quenchquest-api && git pull --ff-only
   sudo cp deploy/nginx-quenchquest-domain.conf /etc/nginx/sites-available/quenchquest
   sudo ln -s /etc/nginx/sites-available/quenchquest /etc/nginx/sites-enabled/quenchquest
   sudo nginx -t && sudo systemctl reload nginx
   ```
3. **HTTPS.** Certbot edits only the file whose server names match:
   ```bash
   sudo certbot --nginx --redirect --cert-name quenchquest -d quenchquestsocialfoundation.org \
        -d www.quenchquestsocialfoundation.org -d api.quenchquestsocialfoundation.org
   ```
4. **API `.env`.** Add the domain to the existing values, and keep the IP entries for now:
   - `ALLOWED_HOSTS` += `api.quenchquestsocialfoundation.org`
   - `CSRF_TRUSTED_ORIGINS` and `CORS_ALLOWED_ORIGINS` += `https://www.quenchquestsocialfoundation.org`
   - `MEDIA_URL=https://api.quenchquestsocialfoundation.org/media/`
   - `CERTIFICATE_VERIFY_URL=https://www.quenchquestsocialfoundation.org/verify`

   Then run `sudo systemctl reload quenchquest-api`.
5. **Rebuild the website.** Set `NEXT_PUBLIC_API_URL=https://api.quenchquestsocialfoundation.org` and
   `NEXT_PUBLIC_SITE_URL=https://www.quenchquestsocialfoundation.org` in `.env.production`, then run
   `deploy-web.sh`; `NEXT_PUBLIC_*` values need a new build. `API_URL` stays `http://127.0.0.1:8081`,
   which the domain config keeps on this machine only.
6. **Turn the IP setup off.** Remove `sites-enabled/quenchquest-ip`, then `nginx -t` and reload.
   Remove the IP entries from `ALLOWED_HOSTS`, CSRF and CORS, then reload the API. Close ports 8080
   and 8081 in the security group.

Certificates already issued keep the **old** IP link in their QR codes. To re-draw them with the
new link, run `POST /api/admin/projects/{id}/certificates/regenerate/` for each project.
