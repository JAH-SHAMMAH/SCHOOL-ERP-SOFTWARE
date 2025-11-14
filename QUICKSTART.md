# Quick Start Guide: Using the New Dashboard Features

## 🚀 Getting Started

### 1. Start the Application

```bash
cd c:\Users\Shammah\Desktop\FAIR-EDUCARE
python main.py
```

Expected output:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 2. Open Browser

Navigate to: `http://localhost:8000`

---

## 👤 Testing Each Role

### ADMIN Account

1. Click "Register User"
2. Fill form:
   - Full Name: `Admin Test`
   - Email: `admin@school.com`
   - Password: `password123`
   - Role: **Admin**
3. Click "Register"
4. Login with these credentials
5. **Expected**: Sidebar with 18+ menu items organized by category

### TEACHER Account

1. Click "Register User"
2. Fill form:
   - Full Name: `Teacher Test`
   - Email: `teacher@school.com`
   - Password: `password123`
   - Role: **Teacher**
3. Click "Register"
4. Login with these credentials
5. **Expected**: Sidebar with 10 menu items (Academic, Records, Engagement, etc.)

### STUDENT Account

1. Click "Register User"
2. Fill form:
   - Full Name: `Student Test`
   - Email: `student@school.com`
   - Password: `password123`
   - Role: **Student**
3. Click "Register"
4. Login with these credentials
5. **Expected**: Sidebar with 5 menu items (My Subjects, My Scores, CBT, etc.)

### PARENT Account

1. Click "Register User"
2. Fill form:
   - Full Name: `Parent Test`
   - Email: `parent@school.com`
   - Password: `password123`
   - Role: **Parent**
3. Click "Register"
4. Login with these credentials
5. **Expected**: Sidebar with 10 menu items (Wallet, Fees, School Store, etc.)

---

## 📋 What to Look For

### After Login

- ✅ Sidebar on left shows role-specific menu
- ✅ Menu items organized by categories
- ✅ Each item has an icon
- ✅ Dashboard displays with welcome message
- ✅ News Feed & Birthdays button visible

### Click Each Menu Item

- ✅ Page content changes
- ✅ Page title updates
- ✅ Content displays properly
- ✅ Forms are visible (if applicable)
- ✅ Tables show data (if applicable)

### Dashboard Features

- ✅ Stat cards showing numbers
- ✅ Class distribution chart
- ✅ Upcoming birthdays list
- ✅ Quick action buttons
- ✅ All links working

---

## 🔍 Detailed Feature Testing

### ADMIN Dashboard

```
1. Dashboard
   ✓ See 4 stat cards (Students, Teachers, Classes, Pending Fees)
   ✓ Click "Refresh Class Distribution" → Chart appears
   ✓ Click "Upcoming Birthdays" → List appears
   ✓ Click "Open Store" → Store items show

2. SMS/WhatsApp
   ✓ See form to compose message
   ✓ Select recipient group
   ✓ See Send SMS and Send WhatsApp buttons

3. E-Classroom
   ✓ See "Create Class" button
   ✓ See example class card

4. Assignments Management
   ✓ See "Create Assignment" button
   ✓ See table for assignments

5. HR Management
   ✓ See 4 stat cards (Total Staff, On Leave, Present, Tasks)

6. Classes Management
   ✓ See "Add Class" button
   ✓ See table of classes

... (and so on for all 18 items)
```

### TEACHER Dashboard

```
1. Dashboard
   ✓ Welcome message with teacher name

2. My Timetable
   ✓ See weekly timetable grid

3. Assignments
   ✓ See "Create Assignment" button
   ✓ See assignments table

4. My Subjects
   ✓ See subject cards

5. Behaviour Tracker
   ✓ See "Log Behaviour" button
   ✓ See behavior records table

... (and so on for all 10 items)
```

### STUDENT Dashboard

```
1. Dashboard
   ✓ Welcome message with student name

2. Rate My Teacher
   ✓ See teacher selection dropdown
   ✓ See 5-star rating system
   ✓ See comments textarea
   ✓ See "Submit Rating" button

3. My Subjects
   ✓ See subject cards with teacher info

4. My Scores
   ✓ See scores table with subject, exam, score, grade

5. CBT
   ✓ See available and completed tests sections
```

### PARENT Dashboard

```
1. Dashboard
   ✓ Welcome message with parent name

2. My Wallet
   ✓ See wallet balance card
   ✓ See total spent card
   ✓ See "Add Funds" button

3. School Fees
   ✓ See fees table with child, term, amount, status

4. Make Payment
   ✓ See payment form
   ✓ Fill in amount
   ✓ Click "Pay Now" → Opens Paystack (if configured)

5. School Store
   ✓ See search box
   ✓ See store items with prices
   ✓ See "Add to Cart" buttons
   ✓ See "View Cart" button

6. Finance Dashboard
   ✓ See 4 cards (Total Due, Paid, Outstanding, Balance)

... (and so on for all 10 items)
```

---

## 🛠️ Troubleshooting

### Problem: Menu items not showing

**Solution**:

1. Press F5 to refresh page
2. Press Ctrl+Shift+Delete to clear cache
3. Close browser and reopen
4. Check browser console (F12) for errors

### Problem: Content not loading when clicking items

**Solution**:

1. Check network tab in F12 for failed requests
2. Verify backend is running
3. Check if API endpoints are available
4. Look for error messages in alerts

### Problem: No data in tables

**Solution**:

1. This is normal - database may be empty
2. Create some test data first (create classes, students, etc.)
3. Data will appear in tables after adding

### Problem: Images not showing in store

**Solution**:

1. This is expected - store items show placeholder descriptions
2. To add images, upload to `/static/fair-educare/images/`
3. Update item records with image URLs

---

## 📊 Database Setup (Optional)

To populate with sample data:

### Create Sample Data Script

```bash
# Run from workspace
python
>>> from main import *
>>> from database import engine, SessionLocal
>>> db_models.Base.metadata.create_all(bind=engine)
>>> db = SessionLocal()
>>> # Add sample classes
>>> cls = db_models.Class(id='1', name='Class 1A', form_name='Form 1')
>>> db.add(cls)
>>> db.commit()
```

---

## 🎓 Feature Descriptions

### Admin Features

- **SMS/WhatsApp**: Send bulk messages to students, parents, or teachers
- **E-Classroom**: Manage online class sessions
- **Assignments**: Create and track student assignments
- **Reports**: View analytics (class distribution, performance)
- **HR Management**: Monitor staff (present, leave, tasks)
- **Medical Records**: Track student health information
- **Visitor Management**: Log school visitors

### Teacher Features

- **Lesson Planner**: Plan lessons and topics
- **Timetable**: View teaching schedule
- **Behaviour Tracker**: Record student behavior
- **Pastoral Care**: Log student support interactions
- **Feedback**: View student ratings and feedback
- **Secondary School Report**: Generate term reports

### Student Features

- **Rate Teacher**: Give feedback to teachers
- **My Scores**: View exam results and grades
- **CBT**: Take online tests
- **My Subjects**: See current subjects and teachers

### Parent Features

- **My Wallet**: Check account balance
- **School Fees**: View and pay fees
- **School Store**: Shop for school items
- **Finance Dashboard**: Summary of all payments
- **Feedback**: Send messages to school
- **Pastoral Care**: Receive school updates

---

## ✅ Verification Checklist

- [ ] Application starts without errors
- [ ] Admin dashboard shows 18+ menu items
- [ ] Teacher dashboard shows 10 menu items
- [ ] Student dashboard shows 5 menu items
- [ ] Parent dashboard shows 10 menu items
- [ ] Each menu item is clickable
- [ ] Content displays when clicked
- [ ] Page titles update appropriately
- [ ] Forms and buttons are visible
- [ ] No JavaScript errors in console (F12)
- [ ] All navigation works smoothly

---

## 📞 Support

If you encounter issues:

1. Check the browser console (F12) for errors
2. Check the terminal where Python is running for server errors
3. Review the documentation files:
   - `FEATURES_IMPLEMENTED.md` - Complete feature list
   - `MENU_STRUCTURE.md` - Menu organization
   - `IMPLEMENTATION_SUMMARY.md` - Technical details

---

## 🎉 You're All Set!

The FAIR-EDUCARE dashboard is now fully functional with:

- ✅ Visible role-based menu items
- ✅ Clickable navigation
- ✅ Actual content for each section
- ✅ Professional UI design
- ✅ Database integration
- ✅ Payment features
- ✅ Store functionality

**Enjoy exploring all the new features!**
