import os
import json
import requests
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from google import genai

# Tải biến môi trường từ file .env
load_dotenv()

app = Flask(__name__)
# Key bí mật quản lý Session cho Flask
app.secret_key = os.getenv("FLASK_SECRET_KEY", "vzcomm_super_secure_secret_key_2026")

# Lấy danh sách Gemini API Keys để dự phòng
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_2")
]
GEMINI_KEYS = [k for k in GEMINI_KEYS if k]


def clean_nation_id(nation_input):
    """
    Hàm chuẩn hóa tên quốc gia:
    Viết thường, thay khoảng trắng thành dấu gạch dưới để gọi API NationStates không bị lỗi 403.
    """
    if not nation_input:
        return ""
    return nation_input.strip().lower().replace(" ", "_")


def get_ns_headers(nation_name, password=None):
    """
    Tạo Header chuẩn tuyệt đối theo quy định bắt buộc của NationStates API.
    """
    nation_id = clean_nation_id(nation_name)
    headers = {
        'User-Agent': f'VzcommAIAdvisor/4.0 (nation:{nation_id}; contact:zhaxuan92@gmail.com)'
    }
    if password:
        headers['X-Password'] = password
    return headers


def ask_gemini_for_choice(nation, ideology, issue_title, issue_text, options):
    """
    Gửi thông tin Issue sang Gemini AI để phân tích và chốt phương án chính xác.
    """
    if not GEMINI_KEYS:
        return None, "⚠️ Chưa cấu hình GEMINI_API_KEY trên biến môi trường Render/Server."

    options_formatted = "\n".join([f"Option ID {opt['id']}: {opt['text']}" for opt in options])

    prompt = f"""
    Bạn là Cố vấn Tối cao của Quốc gia '{nation}'.
    Định hướng chính trị/xã hội của quốc gia: '{ideology}'.

    Vấn đề chính trị/xã hội vừa phát sinh (Issue):
    📌 Tiêu đề: {issue_title}
    📝 Chi tiết: {issue_text}

    Các phương án lựa chọn hiện có:
    {options_formatted}

    YÊU CẦU BẮT BỘC TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON (Không kèm bất kỳ đoạn codeblock hay văn bản nào khác):
    {{
        "chosen_option_id": "MÃ_OPTION_ĐƯỢC_CHỌN",
        "reason": "Giải thích ngắn gọn 2 câu tại sao chọn phương án này dựa theo đúng định hướng quốc gia."
    }}
    """

    for idx, key in enumerate(GEMINI_KEYS):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            raw_text = response.text.strip()

            # Lọc bỏ markdown codeblock nếu có
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            data = json.loads(raw_text.strip())
            return data.get("chosen_option_id"), data.get("reason")
        except Exception as e:
            print(f"[DEBUG] Gemini Key {idx + 1} gặp sự cố: {e}")
            continue

    return None, "❌ Tất cả API Keys của Gemini đều gặp lỗi hoặc hết hạn hạn mức!"


def fetch_nation_issues(nation, password):
    """
    Truy vấn danh sách các Issue từ NationStates API.
    """
    nation_id = clean_nation_id(nation)
    headers = get_ns_headers(nation_id, password=password)  
# ✅ SỬA THÀNH (Bỏ hoàn toàn dấu [ ]):
url = f"https://www.nationstates.net/cgi-bin/api.cgi?nation={nation_id}&q=issues"

    issues = []
    error_msg = None

    try:
        res = requests.get(url, headers=headers, timeout=12)
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
        elif res.status_code == 403:
            error_msg = f"Lỗi HTTP 403 Forbidden: Mật khẩu hoặc Tên Quốc Gia ({nation_id}) chưa chính xác!"
        else:
            error_msg = f"Lỗi HTTP Status Code {res.status_code} từ NationStates."
    except Exception as e:
        error_msg = f"Lỗi kết nối mạng: {str(e)}"

    return issues, error_msg


def submit_issue_response(nation, password, issue_id, option_id):
    """
    Gửi lựa chọn xử lý Issue trực tiếp lên NationStates API.
    """
    nation_id = clean_nation_id(nation)
    url = "[https://www.nationstates.net/cgi-bin/api.cgi](https://www.nationstates.net/cgi-bin/api.cgi)"
    payload = {
        'nation': nation_id,
        'c': 'issue',
        'issue': str(issue_id),
        'option': str(option_id)
    }
    headers = get_ns_headers(nation_id, password=password)

    try:
        res = requests.post(url, data=payload, headers=headers, timeout=12)
        if res.status_code == 200 and "<ERROR>" not in res.text:
            return True, f"Thành công chọn Option #{option_id}"
        else:
            return False, f"Lỗi phản hồi: {res.text}"
    except Exception as e:
        return False, str(e)


# ==================== CÁC TUYẾN ĐƯỜNG (ROUTES) ====================


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Trang Đăng nhập thông tin"""
    if request.method == 'POST':
        nation = request.form.get('nation', '').strip()
        password = request.form.get('password', '').strip()
        ideology = request.form.get('ideology', 'Tự do & Phát triển').strip()

        if not nation or not password:
            return render_template('login.html', error="Vui lòng nhập đầy đủ Tên Quốc Gia và Mật Khẩu!")

        session['nation'] = nation
        session['password'] = password
        session['ideology'] = ideology
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Trang Quản lý Mật khẩu / Cấu hình Quốc Gia"""
    if 'nation' not in session:
        return redirect(url_for('login'))

    message = None
    if request.method == 'POST':
        new_password = request.form.get('password', '').strip()
        new_ideology = request.form.get('ideology', '').strip()
        
        if new_password:
            session['password'] = new_password
        if new_ideology:
            session['ideology'] = new_ideology
            
        message = "✅ Đã cập nhật thông tin thành công!"

    return render_template(
        'settings.html',
        nation=session.get('nation'),
        password=session.get('password'),
        ideology=session.get('ideology'),
        message=message
    )


@app.route('/logout')
def logout():
    """Đăng xuất tài khoản"""
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
def index():
    """Trang chính hiển thị thông tin & Issues"""
    if 'nation' not in session or 'password' not in session:
        return redirect(url_for('login'))

    nation = session['nation']
    password = session['password']
    clean_id = clean_nation_id(nation)
    issues, api_error = fetch_nation_issues(nation, password)

    # Đường dẫn sang trang web chính thức của game NationStates
    game_url = f"[https://www.nationstates.net/nation=](https://www.nationstates.net/nation=){clean_id}"

    return render_template(
        'index.html',
        nation=nation,
        clean_id=clean_id,
        ideology=session.get('ideology'),
        issues=issues,
        api_error=api_error,
        game_url=game_url
    )


@app.route('/auto_solve_all', methods=['POST'])
def auto_solve_all():
    """API Tự động giải quyết toàn bộ Issues bằng AI"""
    if 'nation' not in session or 'password' not in session:
        return jsonify({'status': 'error', 'message': 'Chưa đăng nhập!'}), 401

    nation = session['nation']
    password = session['password']
    ideology = session.get('ideology', 'Tự do & Phát triển')

    issues, api_error = fetch_nation_issues(nation, password)

    if api_error:
        return jsonify({'status': 'error', 'message': api_error, 'results': []})

    if not issues:
        return jsonify({'status': 'success', 'message': 'Hiện tại không có Issue nào cần xử lý!', 'results': []})

    results = []

    for issue in issues:
        chosen_option_id, reason = ask_gemini_for_choice(
            nation=nation,
            ideology=ideology,
            issue_title=issue['title'],
            issue_text=issue['text'],
            options=issue['options']
        )

        if chosen_option_id:
            success, msg = submit_issue_response(nation, password, issue['id'], chosen_option_id)
            results.append({
                'issue_id': issue['id'],
                'title': issue['title'],
                'chosen_option_id': chosen_option_id,
                'reason': reason,
                'status': 'Thành công' if success else 'Lỗi',
                'detail': msg
            })
        else:
            results.append({
                'issue_id': issue['id'],
                'title': issue['title'],
                'status': 'Lỗi AI',
                'detail': reason
            })

    return jsonify({
        'status': 'success',
        'message': f'Đã xử lý xong {len(results)} Issues!',
        'results': results
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)     
