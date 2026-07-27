import os
import json
import requests
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from google import genai

# Load các biến môi trường từ file .env
load_dotenv()

app = Flask(__name__)

# Cấu hình Secret Key bảo mật cho Session Flask
app.secret_key = os.getenv("FLASK_SECRET_KEY", "vzcomm_secret_key_2026_super_secure")

# Lấy danh sách Gemini API Keys từ môi trường
GEMINI_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_2")
]
GEMINI_KEYS = [k for k in GEMINI_KEYS if k]


def ask_gemini_for_choice(nation, ideology, issue_title, issue_text, options):
    """
    Yêu cầu Gemini AI phân tích Issue và bắt buộc trả về chuỗi JSON chứa option_id cụ thể.
    """
    if not GEMINI_KEYS:
        return None, "⚠️ Chưa cấu hình GEMINI_API_KEY trên Server môi trường."

    options_formatted = "\n".join([f"Option ID {opt['id']}: {opt['text']}" for opt in options])

    prompt = f"""
    Bạn là Cố vấn Tối cao của Quốc gia '{nation}'.
    Định hướng phát triển của quốc gia: '{ideology}'.

    Vấn đề chính trị/xã hội vừa phát sinh:
    📌 Tiêu đề: {issue_title}
    📝 Chi tiết: {issue_text}

    Các phương án lựa chọn:
    {options_formatted}

    YÊU CẦU BẮT BỘC TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON (Không kèm bất kỳ đoạn văn bản nào khác ngoài JSON):
    {{
        "chosen_option_id": "MÃ_OPTION_ĐƯỢC_CHỌN",
        "reason": "Giải thích ngắn gọn 2 câu tại sao chọn phương án này theo đúng định hướng quốc gia."
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

            # Xử lý làm sạch nếu Gemini bọc trong Markdown Code Block
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]

            data = json.loads(raw_text.strip())
            return data.get("chosen_option_id"), data.get("reason")
        except Exception as e:
            print(f"[DEBUG] Gemini Key {idx + 1} bị lỗi: {e}")
            continue

    return None, "❌ Tất cả API Keys của Gemini đều gặp lỗi hoặc đã hết hạn mức truy cập!"


def get_ns_headers(nation_name, password=None):
    """
    Tạo Header chuẩn tuyệt đối theo quy định NationStates API.
    """
    clean_nation = nation_name.strip().lower().replace(" ", "_")
    headers = {
        'User-Agent': f'VzcommAIAdvisor/2.0 (by nation:{clean_nation}; contact:zhaxuan92@gmail.com)'
    }
    if password:
        headers['X-Password'] = password
    return headers


def fetch_nation_issues(nation, password):
    """
    Lấy danh sách các Issue hiện có từ NationStates API.
    """
    headers = get_ns_headers(nation, password=password)
    url = f"[https://www.nationstates.net/cgi-bin/api.cgi?nation=](https://www.nationstates.net/cgi-bin/api.cgi?nation=){nation}&q=issues"
    issues = []

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
    except Exception as e:
        print(f"[DEBUG] Lỗi Fetch Issues từ NationStates: {e}")

    return issues


def submit_issue_response(nation, password, issue_id, option_id):
    """
    Gửi quyết định xử lý Issue lên NationStates API.
    """
    url = "[https://www.nationstates.net/cgi-bin/api.cgi](https://www.nationstates.net/cgi-bin/api.cgi)"
    payload = {
        'nation': nation,
        'c': 'issue',
        'issue': str(issue_id),
        'option': str(option_id)
    }
    headers = get_ns_headers(nation, password=password)

    try:
        res = requests.post(url, data=payload, headers=headers, timeout=12)
        if res.status_code == 200 and "<ERROR>" not in res.text:
            return True, f"Thành công chọn Option #{option_id}"
        else:
            return False, res.text
    except Exception as e:
        return False, str(e)


# ==================== ROUTES HỆ THỐNG ====================


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Trang đăng nhập thông tin quốc gia.
    """
    if request.method == 'POST':
        nation = request.form.get('nation', '').strip().lower().replace(" ", "_")
        password = request.form.get('password', '').strip()
        ideology = request.form.get('ideology', 'Tự do & Phát triển').strip()

        if not nation or not password:
            return render_template('login.html', error="Vui lòng nhập đầy đủ Tên Quốc Gia và Mật Khẩu!")

        session['nation'] = nation
        session['password'] = password
        session['ideology'] = ideology
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    """
    Đăng xuất tài khoản.
    """
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
def index():
    """
    Trang quản lý chính hiển thị Issues.
    """
    if 'nation' not in session or 'password' not in session:
        return redirect(url_for('login'))

    nation = session['nation']
    password = session['password']
    issues = fetch_nation_issues(nation, password)

    return render_template(
        'index.html',
        nation=nation,
        ideology=session.get('ideology'),
        issues=issues
    )


@app.route('/auto_solve_all', methods=['POST'])
def auto_solve_all():
    """
    API Tự động giải quyết toàn bộ Issue có sẵn bằng AI.
    """
    if 'nation' not in session or 'password' not in session:
        return jsonify({'status': 'error', 'message': 'Chưa đăng nhập!'}), 401

    nation = session['nation']
    password = session['password']
    ideology = session.get('ideology', 'Tự do & Phát triển')

    issues = fetch_nation_issues(nation, password)

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
        'message': f'Đã tự động xử lý thành công {len(results)} Issue!',
        'results': results
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
