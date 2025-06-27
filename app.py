import os
import zipfile
import secrets
from datetime import datetime
from functools import wraps

import pandas as pd
import plotly.express as px
import plotly.io as pio
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Configuration
DATA_DIR = 'data'
EXPENSES_FILE = os.path.join(DATA_DIR, 'expenses.xlsx')
BUDGET_FILE = os.path.join(DATA_DIR, 'budget.xlsx')
GOALS_FILE = os.path.join(DATA_DIR, 'goals.xlsx')
PREMIUM_FEATURES = True

os.makedirs(DATA_DIR, exist_ok=True)

# Helper functions
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin', False):
            flash('Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def safe_read_excel(filepath, columns):
    try:
        df = pd.read_excel(filepath, engine='openpyxl')
        for col in columns:
            if col not in df.columns:
                df[col] = None
        return df
    except (FileNotFoundError, ValueError, zipfile.BadZipFile):
        df = pd.DataFrame(columns=columns)
        df.to_excel(filepath, index=False, engine='openpyxl')
        return df

def safe_write_excel(df, filepath):
    try:
        df.to_excel(filepath, index=False, engine='openpyxl')
        return True
    except Exception as e:
        flash(f"Error saving data: {str(e)}", "danger")
        return False

@app.context_processor
def inject_now():
    return {
        'now': datetime.utcnow(),
        'premium_features': PREMIUM_FEATURES,
        'is_admin': session.get('is_admin', False)
    }

# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            hashed_password = generate_password_hash(password)
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error during registration: {str(e)}', 'danger')
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            session['user_id'] = 1
            session['username'] = username
            session['is_admin'] = (username == 'admin')
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Login failed: {str(e)}', 'danger')
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# Main application routes
@app.route('/')
@login_required
def index():
    try:
        exp_df = safe_read_excel(EXPENSES_FILE, ['Date', 'Category', 'Amount', 'Description', 'UserID'])
        user_expenses = exp_df[exp_df['UserID'] == session['user_id']]
        
        total_expense = user_expenses['Amount'].sum() if not user_expenses.empty else 0
        category_summary = user_expenses.groupby('Category')['Amount'].sum().to_dict() if not user_expenses.empty else {}
        
        budget_df = safe_read_excel(BUDGET_FILE, ['Month', 'Category', 'Budget', 'UserID'])
        user_budget = budget_df[budget_df['UserID'] == session['user_id']]
        latest_budget = user_budget.tail(5).to_dict('records') if not user_budget.empty else []
        
        recent_expenses = user_expenses.tail(5).to_dict('records') if not user_expenses.empty else []
        
        spending_chart = None
        if PREMIUM_FEATURES and not user_expenses.empty:
            try:
                user_expenses['Date'] = pd.to_datetime(user_expenses['Date'])
                monthly_spending = user_expenses.groupby(
                    [user_expenses['Date'].dt.strftime('%Y-%m'), 'Category']
                )['Amount'].sum().reset_index()
                fig = px.bar(monthly_spending, x='Date', y='Amount', color='Category',
                             title='Monthly Spending by Category', barmode='stack')
                spending_chart = pio.to_html(fig, full_html=False)
            except Exception as e:
                print(f"Error generating chart: {str(e)}")
        
        return render_template(
            'index.html',
            total=total_expense,
            summary=category_summary,
            expenses=recent_expenses,
            budget=latest_budget,
            spending_chart=spending_chart
        )
    except Exception as e:
        flash(f"Error loading data: {str(e)}", "danger")
        return render_template('index.html', total=0, summary={}, expenses=[], budget=[])

# Expense routes
@app.route('/add-expense', methods=['GET', 'POST'])
@login_required
def add_expense():
    if request.method == 'POST':
        try:
            date = request.form['date']
            category = request.form['category'].strip()
            amount = float(request.form['amount'])
            description = request.form['description'].strip()

            new_expense = pd.DataFrame([{
                'Date': date,
                'Category': category,
                'Amount': amount,
                'Description': description,
                'UserID': session['user_id']
            }])

            df = safe_read_excel(EXPENSES_FILE, ['Date', 'Category', 'Amount', 'Description', 'UserID'])
            df = pd.concat([df, new_expense], ignore_index=True)
            safe_write_excel(df, EXPENSES_FILE)
            flash('Expense added successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error adding expense: {str(e)}', 'danger')
    return render_template('expenses/add_expense.html')

@app.route('/edit-expense/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_expense(id):
    df = safe_read_excel(EXPENSES_FILE, ['Date', 'Category', 'Amount', 'Description', 'UserID'])
    user_expenses = df[df['UserID'] == session['user_id']].reset_index(drop=True)
    
    if request.method == 'POST':
        try:
            idx = df[(df['UserID'] == session['user_id'])].index[id]
            df.at[idx, 'Date'] = request.form['date']
            df.at[idx, 'Category'] = request.form['category']
            df.at[idx, 'Amount'] = float(request.form['amount'])
            df.at[idx, 'Description'] = request.form['description']
            
            safe_write_excel(df, EXPENSES_FILE)
            flash('Expense updated successfully!', 'success')
            return redirect(url_for('view_expenses'))
        except Exception as e:
            flash(f'Error updating expense: {str(e)}', 'danger')
    
    try:
        expense = user_expenses.iloc[id].to_dict()
        return render_template('expenses/edit_expense.html', expense=expense, id=id)
    except IndexError:
        flash('Expense not found!', 'danger')
        return redirect(url_for('view_expenses'))

@app.route('/delete-expense/<int:id>')
@login_required
def delete_expense(id):
    try:
        df = safe_read_excel(EXPENSES_FILE, ['Date', 'Category', 'Amount', 'Description', 'UserID'])
        user_expenses = df[df['UserID'] == session['user_id']]
        
        if id < len(user_expenses):
            idx = user_expenses.index[id]
            df = df.drop(index=idx).reset_index(drop=True)
            safe_write_excel(df, EXPENSES_FILE)
            flash('Expense deleted successfully!', 'success')
        else:
            flash('Expense not found!', 'danger')
    except Exception as e:
        flash(f'Error deleting expense: {str(e)}', 'danger')
    return redirect(url_for('view_expenses'))

@app.route('/view-expenses')
@login_required
def view_expenses():
    try:
        df = safe_read_excel(EXPENSES_FILE, ['Date', 'Category', 'Amount', 'Description', 'UserID'])
        user_expenses = df[df['UserID'] == session['user_id']].to_dict('records')
        return render_template('expenses/view_expense.html', expenses=user_expenses)
    except Exception as e:
        flash(f"Error loading expenses: {str(e)}", "danger")
        return render_template('expenses/view_expense.html', expenses=[])

# Budget routes
@app.route('/add-budget', methods=['GET', 'POST'])
@login_required
def add_budget():
    if request.method == 'POST':
        try:
            month = request.form['month'].strip()
            category = request.form['category'].strip()
            budget = float(request.form['budget'])

            new_budget = pd.DataFrame([{
                'Month': month,
                'Category': category,
                'Budget': budget,
                'UserID': session['user_id']
            }])

            df = safe_read_excel(BUDGET_FILE, ['Month', 'Category', 'Budget', 'UserID'])
            df = pd.concat([df, new_budget], ignore_index=True)
            safe_write_excel(df, BUDGET_FILE)
            flash('Budget added successfully!', 'success')
            return redirect(url_for('view_budget'))
        except Exception as e:
            flash(f'Error adding budget: {str(e)}', 'danger')
    return render_template('budget/add_budget.html')

@app.route('/edit-budget/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_budget(id):
    df = safe_read_excel(BUDGET_FILE, ['Month', 'Category', 'Budget', 'UserID'])
    user_budget = df[df['UserID'] == session['user_id']].reset_index(drop=True)
    
    if request.method == 'POST':
        try:
            idx = df[(df['UserID'] == session['user_id'])].index[id]
            df.at[idx, 'Month'] = request.form['month']
            df.at[idx, 'Category'] = request.form['category']
            df.at[idx, 'Budget'] = float(request.form['budget'])
            
            safe_write_excel(df, BUDGET_FILE)
            flash('Budget updated successfully!', 'success')
            return redirect(url_for('view_budget'))
        except Exception as e:
            flash(f'Error updating budget: {str(e)}', 'danger')
    
    try:
        budget = user_budget.iloc[id].to_dict()
        return render_template('budget/edit_budget.html', budget=budget, id=id)
    except IndexError:
        flash('Budget not found!', 'danger')
        return redirect(url_for('view_budget'))

@app.route('/delete-budget/<int:id>')
@login_required
def delete_budget(id):
    try:
        df = safe_read_excel(BUDGET_FILE, ['Month', 'Category', 'Budget', 'UserID'])
        user_budget = df[df['UserID'] == session['user_id']]
        
        if id < len(user_budget):
            idx = user_budget.index[id]
            df = df.drop(index=idx).reset_index(drop=True)
            safe_write_excel(df, BUDGET_FILE)
            flash('Budget deleted successfully!', 'success')
        else:
            flash('Budget not found!', 'danger')
    except Exception as e:
        flash(f'Error deleting budget: {str(e)}', 'danger')
    return redirect(url_for('view_budget'))

@app.route('/view-budget')
@login_required
def view_budget():
    try:
        df = safe_read_excel(BUDGET_FILE, ['Month', 'Category', 'Budget', 'UserID'])
        user_budget = df[df['UserID'] == session['user_id']].to_dict('records')
        return render_template('budget/view_budget.html', budget=user_budget)
    except Exception as e:
        flash(f"Error loading budget: {str(e)}", "danger")
        return render_template('budget/view_budget.html', budget=[])

# Premium features
@app.route('/financial-goals', methods=['GET', 'POST'])
@login_required
def financial_goals():
    if not PREMIUM_FEATURES:
        flash('Financial goals is a premium feature. Upgrade to access.', 'info')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            goal_name = request.form['goal_name']
            target_amount = float(request.form['target_amount'])
            current_amount = float(request.form.get('current_amount', 0))
            target_date = request.form['target_date']
            priority = request.form['priority']
            
            new_goal = pd.DataFrame([{
                'GoalName': goal_name,
                'TargetAmount': target_amount,
                'CurrentAmount': current_amount,
                'TargetDate': target_date,
                'Priority': priority,
                'UserID': session['user_id']
            }])
            
            df = safe_read_excel(GOALS_FILE, ['GoalName', 'TargetAmount', 'CurrentAmount', 'TargetDate', 'Priority', 'UserID'])
            df = pd.concat([df, new_goal], ignore_index=True)
            safe_write_excel(df, GOALS_FILE)
            flash('Financial goal added successfully!', 'success')
            return redirect(url_for('financial_goals'))
        except Exception as e:
            flash(f'Error adding goal: {str(e)}', 'danger')
    
    try:
        df = safe_read_excel(GOALS_FILE, ['GoalName', 'TargetAmount', 'CurrentAmount', 'TargetDate', 'Priority', 'UserID'])
        user_goals = df[df['UserID'] == session['user_id']].to_dict('records')
        return render_template('premium/financial_goals.html', goals=user_goals)
    except Exception as e:
        flash(f"Error loading goals: {str(e)}", "danger")
        return render_template('premium/financial_goals.html', goals=[])

# Reports
@app.route('/reports')
@login_required
def reports():
    try:
        exp_df = safe_read_excel(EXPENSES_FILE, ['Date', 'Category', 'Amount', 'Description', 'UserID'])
        user_expenses = exp_df[exp_df['UserID'] == session['user_id']]
        
        if not user_expenses.empty:
            user_expenses['Date'] = pd.to_datetime(user_expenses['Date'], errors='coerce')
            user_expenses = user_expenses.dropna(subset=['Date'])
            
            monthly_spending = user_expenses.copy()
            monthly_spending['Month'] = monthly_spending['Date'].dt.strftime('%B %Y')
            monthly_summary = monthly_spending.groupby(['Month', 'Category'])['Amount'].sum().reset_index()
            monthly_data = monthly_summary.to_dict('records')
            
            category_dist = None
            if PREMIUM_FEATURES:
                try:
                    category_summary = user_expenses.groupby('Category')['Amount'].sum().reset_index()
                    fig = px.pie(category_summary, values='Amount', names='Category', 
                                title='Spending by Category', hole=0.3)
                    category_dist = pio.to_html(fig, full_html=False)
                except Exception as e:
                    print(f"Error generating pie chart: {str(e)}")
            
            spending_trends = None
            if PREMIUM_FEATURES:
                try:
                    monthly_trend = user_expenses.groupby(
                        user_expenses['Date'].dt.to_period('M').dt.to_timestamp()
                    )['Amount'].sum().reset_index()
                    fig = px.line(monthly_trend, x='Date', y='Amount', 
                                 title='Monthly Spending Trend', markers=True)
                    spending_trends = pio.to_html(fig, full_html=False)
                except Exception as e:
                    print(f"Error generating line chart: {str(e)}")
            
            return render_template('reports/reports.html', 
                                spending=monthly_data,
                                category_dist=category_dist,
                                spending_trends=spending_trends)
        else:
            return render_template('reports/reports.html', spending=[])
    except Exception as e:
        flash(f"Error generating reports: {str(e)}", "danger")
        return render_template('reports/reports.html', spending=[])

# Admin routes
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        exp_df = safe_read_excel(EXPENSES_FILE, ['Date', 'Category', 'Amount', 'Description', 'UserID'])
        budget_df = safe_read_excel(BUDGET_FILE, ['Month', 'Category', 'Budget', 'UserID'])
        
        total_users = 3  # Demo value
        total_expenses = exp_df['Amount'].sum()
        total_budget = budget_df['Budget'].sum()
        
        return render_template('admin/dashboard.html',
                            total_users=total_users,
                            total_expenses=total_expenses,
                            total_budget=total_budget)
    except Exception as e:
        flash(f"Error loading admin dashboard: {str(e)}", "danger")
        return render_template('admin/dashboard.html')

if __name__ == '__main__':
    app.run(debug=True)