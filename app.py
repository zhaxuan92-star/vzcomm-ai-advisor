import os
import time
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, jsonify
import requests
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError

load_dotenv()

app = Flask(__name__)

# --- CẤU HÌNH BIẾN MÔI TRƯỜNG & API KEYS ---
KEY_1 = os.getenv("GEMINI_API_KEY")
KEY_2 = os.getenv("GEMINI_API_KEY_2")

# Tự động gom các API Key có sẵn trong file .env vào danh sách
API_KEYS = [k for k in [KEY_1, KEY_2] if k]
current_key_index = 0

NATION_NAME = os.getenv("NATION_NAME", "").lower().replace(" ", "_")
NATION_PASSWORD = os.getenv("NATION_PASSWORD")
NATION_IDEOLOGY = os.getenv("NATION_IDEOLOGY", "Tự do và Kinh tế phát triển")

HEADERS = {
    'User-Agent': f'NationStates AI Dashboard Debugger - Nation/{NATION_NAME}'
}

def get_current_ai_client():
    """Khởi tạo Client Gemini từ Key đang được chọn hiện tại"""
    if not API_KEYS:
        return None
    key = API_KEYS[current_key_index]
    return genai.Client(api_key=key)

def get_issues_with_debug():
    """Lấy danh sách các Issues từ NationStates API kèm Header xác thực"""
    url = f"https://www.nationstates.net/cgi-bin/api.cgi?nation={NATION_NAME}&q=issues"
    debug_log = {
        'url': url,
        'status_code': None,
        'raw_xml': '',
        'error': None
    }
    issues = []
    
    headers = HEADERS.copy()
    if NATION_PASSWORD:
        headers['X-Password'] = NATION_PASSWORD

    print(f"\n[DEBUG] 📡 Đang gửi Request tới NationStates API: {url}")
    try:
        res = requests.get(url, headers=headers, timeout=10)
        debug_log['status_code'] = res.status_code
        debug_log['raw_xml'] = res.text
        
        print(f"[DEBUG] 📩 HTTP Status Code: {res.status_code}")
        
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
            debug_log['error'] = f"HTTP Status {res.status_code}"
    except Exception as e:
        print(f"[DEBUG ERROR] ❌ Lỗi kết nối NationStates: {e}")
        debug_log['error'] = str(e)
        
    return issues, debug_log

def extract_best_option_id(ai_text, options):
    """Trích xuất ID lựa chọn do AI đề xuất"""
    for opt in options:
        if f"Option ID: {opt['id']}" in ai_text or f"chọn {opt['id']}" in ai_text.lower():
            return opt['id']
    return options[0]['id'] if options else None

def get_ai_recommendation(title, text, options):
    """Gửi Yêu cầu phân tích tới Gemini AI có hỗ trợ xoay vây 2 API Keys dự phòng"""
    global current_key_index
    
    if not API_KEYS:
        return "⚠️ CẢNH BÁO: Chưa cấu hình GEMINI_API_KEY trong file .env!", None

    opts_formatted = "\n".join([f"Lựa chọn {opt['id']}: {opt['text']}" for opt in options])
    
    prompt = f"""
Bạn là cố vấn tối cao của quốc gia '{NATION_NAME}'.
Định hướng lý tưởng của quốc gia chúng ta là: "{NATION_IDEOLOGY}".

Hãy phân tích Vấn đề (Issue) sau đây:
Tên vấn đề: {title}
Mô tả: {text}

Danh sách lựa chọn:
{opts_formatted}

Nhiệm vụ của bạn:
1. Phân tích ngắn gọn (2-3 câu) tác động của các lựa chọn đến định hướng quốc gia.
2. Đưa ra LỰA CHỌN TỐT NHẤT theo số ID của lựa chọn đó.

Trả về kết quả theo cấu trúc rõ ràng:
- Lời khuyên: [Phân tích ở đây]
- Đề xuất chọn Option ID: [Điền duy nhất ID con số của lựa chọn ở đây, ví dụ: 0 hoặc 1 hoặc 2]
"""

    attempts = 0
    max_attempts = len(API_KEYS)

    while attempts < max_attempts:
        client = get_current_ai_client()
        print(f"[DEBUG] 🤖 Đang dùng Gemini API Key #{current_key_index + 1}...")
        
        try:
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt
            )
            print(f"[DEBUG] ✅ AI (Key #{current_key_index + 1}) phản hồi thành công!")
            return response.text, extract_best_option_id(response.text, options)

        except APIError as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                print(f"[DEBUG WARNING] ⚠️ Key #{current_key_index + 1} hết hạn mức (429)! Đang tự động chuyển sang Key dự phòng...")
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                attempts += 1
                time.sleep(1)
            else:
                print(f"[DEBUG ERROR] ❌ Lỗi Gemini API: {e}")
                return f"Lỗi gọi AI: {e}", None
        except Exception as e:
            print(f"[DEBUG ERROR] ❌ Lỗi không xác định: {e}")
            return f"Lỗi không xác định: {e}", None

    return "❌ CẢNH BÁO: Tất cả các API Key dự phòng đều đã chạm giới hạn sử dụng trong ngày!", None

# --- ROUTES FLASK ---

@app.route('/')
def index():
    """Giao diện chính Cố vấn AI"""
    issues, debug_log = get_issues_with_debug()
    processed_issues = []
    
    for issue in issues:
        advice, recommended_id = get_ai_recommendation(issue['title'], issue['text'], issue['options'])
        issue['ai_advice'] = advice
        issue['recommended_id'] = recommended_id
        processed_issues.append(issue)
        
    return render_template('index.html', issues=processed_issues, nation=NATION_NAME, debug=debug_log)

@app.route('/game')
def game_view():
    """Giao diện mô phỏng trang Issue trên Game gốc để đối chiếu"""
    issues, debug_log = get_issues_with_debug()
    return render_template('game.html', issues=issues, nation=NATION_NAME)

@app.route('/test-ai')
def test_ai():
    """Endpoint kiểm tra thử nghiệm tính năng AI"""
    fake_title = "Vấn đề Giả Lập: Quy hoạch khu kinh tế mới"
    fake_text = "Các nhà đầu tư đề xuất mở rộng khu kinh tế thương mại tự do tại thủ đô."
    fake_options = [
        {'id': '0', 'text': 'Đồng ý mở rộng để phát triển kinh tế nhanh nhất.'},
        {'id': '1', 'text': 'Bỏ qua đề xuất để bảo vệ môi trường.'}
    ]
    advice, recommended_id = get_ai_recommendation(fake_title, fake_text, fake_options)
    return jsonify({
        'status': 'success',
        'active_key_index': current_key_index + 1,
        'ai_raw_response': advice,
        'extracted_option_id': recommended_id
    })

@app.route('/respond', methods=['POST'])
def respond_issue():
    """Endpoint gửi quyết định Issue lên NationStates API"""
    issue_id = request.form.get('issue_id')
    option_id = request.form.get('option_id')
    
    url = "https://www.nationstates.net/cgi-bin/api.cgi"
    payload = {
        'nation': NATION_NAME,
        'c': 'issue',
        'issue': issue_id,
        'action': 'respond',
        'choice': option_id
    }
    
    headers = HEADERS.copy()
    headers['X-Password'] = NATION_PASSWORD
    
    print(f"[DEBUG] 📤 Gửi quyết định Issue #{issue_id}, Option ID: {option_id}...")
    res = requests.post(url, data=payload, headers=headers)
    print(f"[DEBUG] 📥 Kết quả gửi: HTTP {res.status_code} | Body: {res.text}")
    
    if res.status_code == 200 and "Error" not in res.text:
        return jsonify({'status': 'success', 'message': f'Đã giải quyết Issue #{issue_id} thành công!'})
    else:
        return jsonify({'status': 'error', 'message': f'Lỗi từ NationStates API: {res.text}'}), 400
        
# --- NHÁNH QUÂN ĐỘI MẠNG NỘI BỘ (INAV SECRET ROUTE) ---

# Mã PIN bảo mật đăng nhập căn cứ INAV
INAV_SECRET_PIN = "755147597"  # Mã PIN Debug Flask của bạn (viết liền không dấu gạch)

@app.route('/Vzcomm/access-secret/INAV', methods=['GET', 'POST'])
def inav_secret_base():
    """Căn cứ Quân đội Mạng Nội bộ Vzcomm (INAV)"""
    auth_status = False
    ai_strategy_response = None
    error_msg = None

    if request.method == 'POST':
        user_pin = request.form.get('inav_pin', '').replace('-', '').strip()
        user_prompt = request.form.get('military_prompt', '')

        # Kiểm tra mã PIN xác thực
        if user_pin == INAV_SECRET_PIN:
            auth_status = True
            
            # Nếu người dùng gửi yêu cầu bàn tác chiến quân sự
            if user_prompt:
                inav_system_prompt = f"""
[MẬT - CHỈ NỘI BỘ QUÂN ĐỘI MẠNG INAV VZCOMM]
Bạn là Đại Tá AI - Hệ thống Trí tuệ Nhân tạo chỉ huy thuộc Bộ Quốc phòng Mạng Quốc gia {NATION_NAME.upper()}.
Mục tiêu tối cao: Bảo vệ an ninh mạng, phát triển sức mạnh quân sự, bảo vệ tư tưởng: "{NATION_IDEOLOGY}".

Hãy phân tích chiến thuật và đưa ra đề xuất tác chiến quân sự/ngoại giao cho yêu cầu sau từ Tối cao Pháp viện:
"{user_prompt}"

Phong cách trả lời: Quát tháo ngắn gọn, kỷ luật quân đội, mang tính chiến thuật cao, trình bày dạng mệnh lệnh quân sự (Dùng các icon 🎖️, 🛡️, ⚔️, 📡).
"""
                # Gọi Gemini AI trả lời theo phong cách Chỉ huy INAV
                try:
                    client = get_current_ai_client()
                    if client:
                        res = client.models.generate_content(
                            model='gemini-3.6-flash',
                            contents=inav_system_prompt
                        )
                        ai_strategy_response = res.text
                    else:
                        error_msg = "Không tìm thấy API Key Gemini hợp lệ!"
                except Exception as e:
                    error_msg = f"Lỗi máy chủ INAV: {e}"
        else:
            error_msg = "❌ BÁO ĐỘNG SẮC ĐỎ: MÃ PIN XÁC THỰC INAV KHÔNG CHÍNH XÁC! TRUY CẬP BỊ TỪ CHỐI."

    return render_template(
        'inav_secret.html', 
        auth_status=auth_status, 
        ai_response=ai_strategy_response, 
        error_msg=error_msg,
        nation=NATION_NAME
    )
    
if __name__ == '__main__':
    print("🚀 App Flask Debug Mode đang khởi chạy...")
    app.run(debug=True, port=5000)
