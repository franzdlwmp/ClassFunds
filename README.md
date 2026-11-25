# ClassFunds

A Django web app for class treasurers: collections, payments, expenses, cash-outs, remittances and reports.

## Setup (first time)

1. Clone the repository and open the project folder in Command Prompt.
2. Create and activate a virtual environment:

   ```
   python -m venv venv
   venv\Scripts\activate
   ```

3. Install the requirements:

   ```
   pip install -r requirements.txt
   ```

4. Create the database tables:

   ```
   python manage.py migrate
   ```

5. Create the first admin account (the database starts empty, so nobody can log in until this exists):

   ```
   python manage.py createsuperuser
   ```

   Enter a username and password when asked. The password stays hidden while you type, and email can be left blank unless it asks for it.

6. (Optional) Add sample data (Including sample treasurer login details, read "seed_demo.py" in finance/management/commands):

   ```
   python manage.py seed_demo
   ```

7. Start the server and open http://127.0.0.1:8000/ :

   ```
   python manage.py runserver
   ```

Sign in with the account from step 5. From the admin pages you can create courses, sections and treasurers.

## Troubleshooting

- **no such table:** run `python manage.py migrate` first.
- **No module named django:** activate the virtual environment (`venv\Scripts\activate`).
- **can't open file manage.py:** you are in the wrong folder; `cd` into the project folder that contains `manage.py`.