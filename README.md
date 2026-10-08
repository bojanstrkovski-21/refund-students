# Поврат на патни трошоци

Local book for refunding student travel expenses at СОУ „Таки Даскало“ - Битола. One login, one SQLite file, works offline.

## Run

**Windows:** double-click `start.bat`, then open [http://127.0.0.1:5050](http://127.0.0.1:5050).

```bash
pip install -r requirements.txt
python app.py
```

First login: `admin` / `admin123`. Change that password after the first login.

This app uses port 5050 so it can run next to the invoice book on port 5000. It listens only on this computer.

## What it keeps

Each student has a last name, a first name, a class, and the parent name. Class is one of 4 years and 12 sections, stored as `I-3`. Parent EMBG (13 digits) and the bank account (15 digits) can be added later. Leading zeros stay. A checksum mistake on EMBG is only a warning. The first three digits of the account show the bank name.

Travel bills are dated amounts, with an optional note. The total sits at the bottom of the student sheet and updates as you type. The month above the bills starts as the previous month. Dates and the save use only that month. Bills from other months stay in the file.

An admin can edit and delete. A normal user can add a student and add bills.

## Reports

- **Месечен преглед** — one line per student for that month, with a total. An admin marks the whole month paid here.
- **Сметки за месецот** — every bill in that month, grouped by student.
- **Ученик / месец** — one parent and one month, with every bill and a total.
- **Ученик / родител** — all bills for one student, by month.
- **Година** — every student, twelve months, and which months are paid.

Each report exports to Excel. EMBG and bank account stay text, so Excel does not drop the leading zero.

If a bill is added after a month is marked paid, the month shows a warning until an admin marks it again.

## Backup

Copy `refunds.db`. That file is the whole book.
