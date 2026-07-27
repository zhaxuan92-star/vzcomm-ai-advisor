import os
import requests
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from google import genai

# Tải biến môi trường từ file .env
load_dotenv()

app = Flask(__name__)

# Cấu hình Secret Key mã hóa Session
app.secret_key = os.getenv("FLASK_SECRET_KEY", "vzcomm_secret_key_2026_super_secure")

# Cấu hình danh sách Gemini API Keys để xoay vòng (Fallback)
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_2")
]
GEMINI_KEYS = [k for k in GEMINI_KEYS if k]

def ask_gemini(prompt_text):
    """
    Hàm gọi Gemini AI với cơ chế xoay vòng API Key dự phòng.
    """
    if not GEMINI_KEYS:
        return "⚠️ Chưa cấu hình GEMINI_API_KEY trên Server môi trường."
        
    for idx, key in enumerate(GEMINI_KEYS):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt_text,
            )
            return response.text
        except Exception as e:
            print(f"[DEBUG] Gemini Key {idx+1} bị lỗi hoặc hết hạn: {e}")
            continue
            
    return "❌ Tất cả API Keys của Gemini đều gặp lỗi hoặc đã hết hạn mức truy cập!"

def get_ns_headers(nation_name, password=None):
    """
    Tạo Header chuẩn tuyệt đối theo quy định của NationStates API:
    1. User-Agent bắt buộc định dạng chuẩn.
    2. Gửi kèm X-Password nếu truy cập Private Shards / Private Commands.
    """
    clean_nation = nation_name.strip().lower().replace(" ", "_")
    headers = {
        'User-Agent': f'VzcommAIAdvisor/2.0 (by nation:{clean_nation}; contact:zhaxuan92@gmail.com)'
    }
    if password:
        headers['X-Password'] = password
    return headers

# ==================== ROUTES QUẢN LÝ TÀI KHOẢN & SESSION ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Trang đăng nhập quốc gia, lưu thông tin vào Session.
    """
    if request.method == 'POST':
        nation = request.form.get('nation', '').strip().lower().replace(" ", "_")
        password = request.form.get('password', '').strip()
        ideology = request.form.get('ideology', 'Tự do & Phát triển').strip()
        
        if not nation or not password:
            return render_template('login.html', error="Vui lòng nhập đầy đủ Tên Quốc Gia và Mật Khẩu!")
            
        # Lưu dữ liệu quốc gia vào Session
        session['nation'] = nation
        session['password'] = password
        session['ideology'] = ideology
        
        return redirect(url_for('index'))
        
    return render_template('login.html')

@app.route('/logout')
def logout():
    """
    Đăng xuất khỏi quốc gia hiện tại và xóa thông tin Session.
    """
    session.clear()
    return redirect(url_for('login'))

# ==================== ROUTES XỬ LÝ NỘI DUNG CHÍNH ====================

@app.route('/')
def index():
    """
    Trang chủ Cố vấn AI: Tải danh sách Issue từ NationStates API (Private Shard).
    """
    if 'nation' not in session or 'password' not in session:
        return redirect(url_for('login'))
        
    nation = session['nation']
    password = session['password']
    
    # QUAN TRỌNG: Private Shards (q=issues) bắt buộc phải truyền X-Password để không bị HTTP 403
    headers = get_ns_headers(nation, password=password)
    
    url = f"https://www.nationstates.net/cgi-bin/api.cgi?nation={nation}&q=issues"
    debug_log = {
        'url': url, 
        'status_code': None, 
        'raw_xml': '', 
        'error': None
    }
    issues = []
    
    try:
        req_session = requests.Session()
        res = req_session.get(url, headers=headers, timeout=12)
        
        debug_log['status_code'] = res.status_code
        debug_log['raw_xml'] = res.text
        
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for issue_node in root.findall('.//ISSUE'):
                issue_id = issue_node.attrib.get('id')
                title = issue_node.find('TITLE').text if issue_node.find('TITLE') is not None else ''
                text = issue_node.find('TEXT').text if issue_node.find('TEXT') is not None else ''
                
                options = []
                for opt in issue_node.findall('.//OPTION'):
                    options.append({
                        'id': opt.attrib.get('id'),
                        'text': opt.text
                    })
                
                issues.append({
                    'id': issue_id, 
                    'title': title, 
                    'text': text, 
                    'options': options
                })
        else:
            debug_log['error'] = f"HTTP Status Code {res.status_code}"
    except Exception as e:
        debug_log['error'] = str(e)
        
    return render_template(
        'index.html', 
        nation=nation, 
        ideology=session.get('ideology'), 
        issues=issues, 
        debug=debug_log
    )

@app.route('/analyze_issue', methods=['POST'])
def analyze_issue():
    """
    Nhận yêu cầu phân tích Issue và chuyển giao ngữ cảnh cho AI Gemini xử lý.
    """
    if 'nation' not in session:
        return jsonify({'status': 'error', 'message': 'Chưa đăng nhập quốc gia!'}), 401
        
    data = request.json
    issue_title = data.get('title')
    issue_text = data.get('text')
    options = data.get('options', [])
    
    options_text = "\n".join([f"- Lựa chọn {opt['id']}: {opt['text']}" for opt in options])
    
    prompt = f"""
    Bạn là Cố vấn Tối cao của Quốc gia '{session['nation']}'.
    Định hướng phát triển của quốc gia: '{session.get('ideology')}'.
    
    Vấn đề chính trị/xã hội vừa phát sinh:
    📌 Tiêu đề: {issue_title}
    📝 Chi tiết: {issue_text}
    
    Các phương án lựa chọn:
    {options_text}
    
    Yêu cầu:
    1. Phân tích ngắn gọn tác động của từng phương án đến kinh tế, chính trị, tự do dân quyền.
    2. Đưa ra khuyến nghị chọn Option nào tối ưu nhất theo đúng định hướng quốc gia.
    3. Trả lời với phong cách trang trọng, sắc bén của một Cố vấn Tối cao.
    """
    
    ai_response = ask_gemini(prompt)
    return jsonify({'status': 'success', 'analysis': ai_response})

@app.route('/respond', methods=['POST'])
def respond_issue():
    """
    Gửi quyết định của người chơi lên API chính thức của NationStates (Private Command: c=issue).
    """
    if 'nation' not in session or 'password' not in session:
        return jsonify({'status': 'error', 'message': 'Chưa đăng nhập quốc gia!'}), 401
        
    issue_id = request.form.get('issue_id')
    option_id = request.form.get('option_id')
    
    nation = session['nation']
    password = session['password']
    
    url = "https://www.nationstates.net/cgi-bin/api.cgi"
    payload = {
        'nation': nation,
        'c': 'issue',
        'issue': str(issue_id),
        'option': str(option_id)
    }
    
    # Private Commands bắt buộc truyền X-Password
    headers = get_ns_headers(nation, password=password)
    
    try:
        req_session = requests.Session()
        res = req_session.post(url, data=payload, headers=headers, timeout=12)
        if res.status_code == 200 and "<ERROR>" not in res.text:
            return jsonify({'status': 'success', 'message': f'Đã giải quyết thành công Issue #{issue_id} với Lựa chọn {option_id}!'})
        else:
            return jsonify({'status': 'error', 'message': f'NationStates phản hồi lỗi: {res.text}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Lỗi kết nối tới Server NationStates: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
            )
            return response.text
        except Exception as e:
            print(f"[DEBUG] Gemini Key {idx+1} bị lỗi hoặc hết hạn: {e}")
            continue
            
    return "❌ Tất cả API Keys của Gemini đều gặp lỗi hoặc đã hết hạn mức truy cập!"

def get_ns_headers(nation_name):
    """
    Tạo Header chuẩn tuyệt đối theo quy định của NationStates API.
    Định dạng: <AppName>/<Version> (by <NationName>; contact:<Email>)
    """
    clean_nation = nation_name.strip().lower().replace(" ", "_")
    return {
        'User-Agent': f'VzcommAIAdvisor/2.0 (by nation:{clean_nation}; contact:zhaxuan92@gmail.com)'
    }

# ==================== ROUTES QUẢN LÝ TÀI KHOẢN & SESSION ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Trang đăng nhập quốc gia, lưu thông tin vào Session.
    """
    if request.method == 'POST':
        nation = request.form.get('nation', '').strip().lower().replace(" ", "_")
        password = request.form.get('password', '').strip()
        ideology = request.form.get('ideology', 'Tự do & Phát triển').strip()
        
        if not nation or not password:
            return render_template('login.html', error="Vui lòng nhập đầy đủ Tên Quốc Gia và Mật Khẩu!")
            
        # Lưu dữ liệu quốc gia vào Session
        session['nation'] = nation
        session['password'] = password
        session['ideology'] = ideology
        
        return redirect(url_for('index'))
        
    return render_template('login.html')

@app.route('/logout')
def logout():
    """
    Đăng xuất khỏi quốc gia hiện tại và xóa thông tin Session.
    """
    session.clear()
    return redirect(url_for('login'))

# ==================== ROUTES XỬ LÝ NỘI DUNG CHÍNH ====================

@app.route('/')
def index():
    """
    Trang chủ Cố vấn AI: Tải danh sách Issue từ NationStates API.
    """
    if 'nation' not in session:
        return redirect(url_for('login'))
        
    nation = session['nation']
    password = session['password']
    headers = get_ns_headers(nation)
    
    url = f"https://www.nationstates.net/cgi-bin/api.cgi?nation={nation}&q=issues"
    debug_log = {
        'url': url, 
        'status_code': None, 
        'raw_xml': '', 
        'error': None
    }
    issues = []
    
    try:
        # Sử dụng Session của requests để đảm bảo connection và headers giữ nguyên
        req_session = requests.Session()
        res = req_session.get(url, headers=headers, timeout=12)
        
        debug_log['status_code'] = res.status_code
        debug_log['raw_xml'] = res.text
        
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for issue_node in root.findall('.//ISSUE'):
                issue_id = issue_node.attrib.get('id')
                title = issue_node.find('TITLE').text if issue_node.find('TITLE') is not None else ''
                text = issue_node.find('TEXT').text if issue_node.find('TEXT') is not None else ''
                
                options = []
                for opt in issue_node.findall('.//OPTION'):
                    options.append({
                        'id': opt.attrib.get('id'),
                        'text': opt.text
                    })
                
                issues.append({
                    'id': issue_id, 
                    'title': title, 
                    'text': text, 
                    'options': options
                })
        else:
            debug_log['error'] = f"HTTP Status Code {res.status_code}"
    except Exception as e:
        debug_log['error'] = str(e)
        
    return render_template(
        'index.html', 
        nation=nation, 
        ideology=session.get('ideology'), 
        issues=issues, 
        debug=debug_log
    )

@app.route('/analyze_issue', methods=['POST'])
def analyze_issue():
    """
    Nhận yêu cầu phân tích Issue và chuyển giao ngữ cảnh cho AI Gemini xử lý.
    """
    if 'nation' not in session:
        return jsonify({'status': 'error', 'message': 'Chưa đăng nhập quốc gia!'}), 401
        
    data = request.json
    issue_title = data.get('title')
    issue_text = data.get('text')
    options = data.get('options', [])
    
    options_text = "\n".join([f"- Lựa chọn {opt['id']}: {opt['text']}" for opt in options])
    
    prompt = f"""
    Bạn là Cố vấn Tối cao của Quốc gia '{session['nation']}'.
    Định hướng phát triển của quốc gia: '{session.get('ideology')}'.
    
    Vấn đề chính trị/xã hội vừa phát sinh:
    📌 Tiêu đề: {issue_title}
    📝 Chi tiết: {issue_text}
    
    Các phương án lựa chọn:
    {options_text}
    
    Yêu cầu:
    1. Phân tích ngắn gọn tác động của từng phương án đến kinh tế, chính trị, tự do dân quyền.
    2. Đưa ra khuyến nghị chọn Option nào tối ưu nhất theo đúng định hướng quốc gia.
    3. Trả lời với phong cách trang trọng, sắc bén của một Cố vấn Tối cao.
    """
    
    ai_response = ask_gemini(prompt)
    return jsonify({'status': 'success', 'analysis': ai_response})

@app.route('/respond', methods=['POST'])
def respond_issue():
    """
    Gửi quyết định của người chơi lên API chính thức của NationStates.
    """
    if 'nation' not in session:
        return jsonify({'status': 'error', 'message': 'Chưa đăng nhập quốc gia!'}), 401
        
    issue_id = request.form.get('issue_id')
    option_id = request.form.get('option_id')
    
    nation = session['nation']
    password = session['password']
    
    url = "https://www.nationstates.net/cgi-bin/api.cgi"
    payload = {
        'nation': nation,
        'c': 'issue',
        'issue': str(issue_id),
        'action': 'respond',
        'option': str(option_id)
    }
    
    headers = get_ns_headers(nation)
    headers['X-Password'] = password
    
    try:
        req_session = requests.Session()
        res = req_session.post(url, data=payload, headers=headers, timeout=12)
        if res.status_code == 200 and "<ERROR>" not in res.text:
            return jsonify({'status': 'success', 'message': f'Đã giải quyết thành công Issue #{issue_id} với Lựa chọn {option_id}!'})
        else:
            return jsonify({'status': 'error', 'message': f'NationStates phản hồi lỗi: {res.text}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Lỗi kết nối tới Server NationStates: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
