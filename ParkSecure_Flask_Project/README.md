# ParkSecure — Flask version

## Files
- `app.py` — Flask backend, SQLite database setup, authentication and reservation logic
- `templates/index.html` — login/register page
- `templates/dashboard.html` — parking dashboard
- `static/style.css` — responsive styling
- `static/app.js` — slot selection, availability and reservation list behavior
- `parking.db` — created automatically when you run the app

## Run in VS Code (Windows)
1. Extract this ZIP and open the `ParkSecure_Flask_Project` folder in VS Code.
2. Open **Terminal → New Terminal**.
3. (Optional but recommended) create a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   If PowerShell blocks activation, you can use `.\.venv\Scripts\python.exe -m pip install Flask` and then `.\.venv\Scripts\python.exe app.py` instead.
4. Install Flask:
   ```powershell
   python -m pip install Flask
   ```
5. Run:
   ```powershell
   python app.py
   ```
6. Visit **http://127.0.0.1:5000**.
7. Create an account, check future parking times, select an available slot and reserve it.

Python's built-in `sqlite3` is used, so you do not need Node.js, npm, MySQL, or a native SQLite package.

## Security features demonstrated
- Passwords are stored as Werkzeug password hashes, not plaintext.
- Parameterized SQL queries.
- Session cookies configured HttpOnly and SameSite=Lax.
- CSRF tokens checked on POST requests.
- Server-side validation for names, email, password and reservation times.
- SQLite `BEGIN IMMEDIATE` transaction with a fresh overlap check before inserting a reservation.
- Users can see and cancel only their own reservations.
- Security headers including CSP, X-Frame-Options and nosniff.

## Suggested test cases
1. Register with a password under 8 characters: rejected.
2. Register with the same email twice: rejected.
3. Login with a wrong password: rejected.
4. Reserve a slot and check that it becomes unavailable for overlapping time.
5. Try end time before start time: rejected.
6. Try a reservation longer than 24 hours: rejected.
7. Cancel an upcoming reservation and verify the slot is available again.
8. Log in with a second account and verify the first account's reservations are not shown.

## Notes
This is a local educational demo, not a production deployment. Before deployment, set a strong random `SESSION_SECRET` environment variable, disable Flask debug mode, use HTTPS, add authentication rate limiting and operational monitoring, and use a persistent production session strategy. Do not use real passwords.
