# Setup Guid

1. Clone this repo.
2. Replace all references of blueprint by YOUR_CHOICE. Notice that the spelling mistake is intentional.
3. Don't forget to rename folders as well.
4. Duplicate .env.example as .env and set things accordingly. Take a moment to look at the used ports. (docker ps). Also leave FORCE_SCRIPT_NAME empty for dev.

```bash
cp .env.example .env
```

5. (Production Only) Run

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

6. (Dev Only) Run

```bash
docker compose up -d --build
```

7. Create a superuser

```bash
docker compose -f docker-compose.yml run --rm web bash
python manage.py createsuperuser
```

8. Go to https://domain.com/api/admin