import os
import json
from flask import Flask, render_template, request, redirect, url_for, session, flash
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from collections import defaultdict
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'your_very_secret_key_here') # Replace with a strong, random key in production

# Simple password for demonstration
CORRECT_PASSWORD = "1018"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('로그인이 필요합니다.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_sheet_data():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

        # API 키를 환경 변수에서 읽어옴
        creds_json_str = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        if not creds_json_str:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS_JSON environment variable not set.")

        creds_info = json.loads(creds_json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, scope)

        client = gspread.authorize(creds)
        sheet = client.open("스마트스토어").worksheet("발주발송관리")
        
        # Get all values from the sheet
        all_values = sheet.get_all_values()
        if not all_values:
            return []

        # Manually create list of dicts with cleaned headers
        headers = [h.strip() for h in all_values[0]]
        data = []
        for row_values in all_values[1:]:
            row_dict = {headers[i]: val for i, val in enumerate(row_values)}
            data.append(row_dict)
        return data

    except FileNotFoundError:
        return [{"error": "credentials.json not found. Please follow setup instructions."}]
    except gspread.exceptions.SpreadsheetNotFound:
        return [{"error": "Spreadsheet not found. Please check the name and sharing settings."}]
    except gspread.exceptions.WorksheetNotFound:
        return [{"error": "Worksheet '발주발송관리' not found. Please check the worksheet name."}]
    except Exception as e:
        return [{"error": f"An unexpected error occurred: {e}"}]

@app.route('/')
def root():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        if password == CORRECT_PASSWORD:
            session['logged_in'] = True
            flash('로그인 성공!', 'success')
            return redirect(url_for('orders'))
        else:
            flash('비밀번호가 틀렸습니다.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('로그아웃 되었습니다.', 'info')
    return redirect(url_for('login'))

@app.route('/orders')
@login_required
def orders():
    data = get_sheet_data()
    if not data or (isinstance(data[0], dict) and data[0].get("error")):
        return render_template('orders.html', orders_by_product={}, error=data[0].get("error") if data else "Unknown error")

    # Get unique delivery dates for the filter dropdown
    delivery_dates = sorted(list(set(row.get('배송희망일') for row in data if row.get('배송희망일'))))

    # Filter data based on selected date
    selected_date = request.args.get('delivery_date')
    if selected_date and selected_date != 'all':
        main_order_ids = set(row['주문번호'] for row in data if row.get('배송희망일') == selected_date and row.get('상품종류') == '조합형옵션상품')
        data = [row for row in data if row.get('주문번호') in main_order_ids]

    # 1. Group by product for tabs
    tabs = defaultdict(list)
    for row in data:
        if '관리용상품명' in row:
            tabs[row['관리용상품명']].append(row)

    # 2. Group orders by order number within each tab
    orders_by_product = defaultdict(dict)
    for product_name, rows in tabs.items():
        grouped_orders = defaultdict(lambda: {'main_info': None, 'sub_products': []})
        for row in rows:
            order_id = row.get('주문번호')
            if not order_id:
                continue

            if row.get('상품종류') == '조합형옵션상품':
                grouped_orders[order_id]['main_info'] = row
            elif row.get('상품종류') == '추가구성상품':
                grouped_orders[order_id]['sub_products'].append(row)
        
        sorted_orders = sorted(grouped_orders.items(), key=lambda item: item[0])
        orders_by_product[product_name] = dict(sorted_orders)

    return render_template('orders.html', 
                           orders_by_product=orders_by_product, 
                           delivery_dates=delivery_dates,
                           selected_date=selected_date)

if __name__ == '__main__':
    app.run(debug=True)
