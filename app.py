import os
import requests
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from google import genai

load_dotenv()

app = Flask(__name__)
# Key bí mật để mã hóa Session đăng nhập của người dùng
app.secret_key = os.getenv("FLASK_SECRET_KEY", "vzcomm_secret_key_2026_super_secure")

# Cấu hình Gemini API Keys
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_2")
]
GEMINI_KEYS = [k for k in GEMINI_KEYS if k]

def ask_gemini(prompt_text):
    """Hàm gọi Gemini AI với cơ chế xoay API Key linh hoạt"""
    if not GEMINI_KEYS:
        return "⚠️ Chưa cấu hình GEMINI_API_KEY trên Server."
        
    for idx, key in enumerate(GEMINI_KEYS):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt_text,
            )
            return response.text
        except Exception as e:
            print(f"[DEBUG] Key {idx+1} lỗi: {e}")
            continue
    return "❌ Tất cả API Keys đều gặp lỗi hoặc hết hạn mức!"

def get_ns_headers(nation_name):
    """Tạo Header chuẩn hóa đúng quy định NationStates API (Tránh bị khóa IP)"""
    return {
        'User-Agent': f'VzcommAIAdvisor/2.0 (Maintained by Nation:{nation_name}; Interactive AI Advisor Project)'
    }

# ==================== ROUTES QUẢN LÝ TÀI KHOẢN ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Trang đăng nhập quốc gia"""
    if request.method == 'POST':
        nation = request.form.get('nation', '').strip().lower().replace(" ", "_")
        password = request.form.get('password', '').strip()
        ideology = request.form.get('ideology', 'Tự do & Phát triển').strip()
        
        if not nation or not password:
            return render_template('login.html', error="Vui lòng nhập đầy đủ Tên Quốc Gia và Mật Khẩu!")
            
        # Lưu vào Session của trình duyệt
        session['nation'] = nation
        session['password'] = password
        session['ideology'] = ideology
        
        return redirect(url_for('index'))
        
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Xóa Session - Đăng xuất khỏi quốc gia hiện tại"""
    session.clear()
    return redirect(url_for('login'))

# ==================== ROUTES CHÍNH ====================

@app.route('/')
def index():
    """Trang chủ Cố vấn AI"""
    if 'nation' not in session:
        return redirect(url_for('login'))
        
    nation = session['nation']
    password = session['password']
    headers = get_ns_headers(nation)
    
    url = f"https://www.nationstates.net/cgi-bin/api.cgi?nation={nation}&q=issues"
    debug_log = {'url': url, 'status_code': None, 'raw_xml': '', 'error': None}
    issues = []
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
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
                
                issues.append({'id': issue_id, 'title': title, 'text': text, 'options': options})
        else:
            debug_log['error'] = f"HTTP {res.status_code}"
    except Exception as e:
        debug_log['error'] = str(e)
        
    return render_template('index.html', 
                           nation=nation, 
                           ideology=session.get('ideology'), 
                           issues=issues, 
                           debug=debug_log)

@app.route('/analyze_issue', methods=['POST'])
def analyze_issue():
    """Nhận yêu cầu phân tích Issue từ giao diện và gửi cho Gemini"""
    if 'nation' not in session:
        return jsonify({'status': 'error', 'message': 'Chưa đăng nhập!'}), 401
        
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
    1. Phân tích ngắn gọn tác động của từng phương án.
    2. Đưa ra khuyến nghị chọn Option nào tối ưu nhất theo định hướng quốc gia.
    3. Trả lời với phong cách trang trọng, sắc bén của một Cố vấn Tối cao.
    """
    
    ai_response = ask_gemini(prompt)
    return jsonify({'status': 'success', 'analysis': ai_response})

@app.route('/respond', methods=['POST'])
def respond_issue():
    """Thực thi quyết định do Người chơi duyệt gửi lên NationStates API"""
    if 'nation' not in session:
        return jsonify({'status': 'error', 'message': 'Chưa đăng nhập!'}), 401
        
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
    headers['X-Password'] = password # Xác thực quyền sở hữu hợp lệ
    
    try:
        res = requests.post(url, data=payload, headers=headers, timeout=10)
        if res.status_code == 200 and "<ERROR>" not in res.text:
            return jsonify({'status': 'success', 'message': f'Đã giải quyết Issue #{issue_id} với Lựa chọn {option_id}!'})
        else:
            return jsonify({'status': 'error', 'message': f'NationStates phản hồi: {res.text}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Lỗi kết nối: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
