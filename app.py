import json
import os
from math import floor

import qrcode
import requests
from PIL import Image, ImageFont
from PIL import ImageDraw
from uuid import uuid4

from barcode import EAN13, Code128
from barcode.writer import ImageWriter  # 載入 barcode.writer 的 ImageWriter

from flask import Flask, request, abort, render_template, jsonify, redirect, url_for
from dotenv import load_dotenv
from future.backports.datetime import datetime
from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage, TemplateMessage, ButtonsTemplate, MessageAction, URIAction, ImageMessage, PostbackAction, FlexMessage,
    FlexCarousel
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent, PostbackEvent
)
from pillow_heif import register_heif_opener

from template import flex

app = Flask(__name__, static_folder='static')
load_dotenv()

configuration = Configuration(access_token=os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))
register_heif_opener()


@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        if event.message.text == "我不吃牛肉":
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(text='好的，我們將不會提供牛肉給您'),
                        FlexMessage(
                            alt_text='功能表',
                            contents=FlexCarousel.from_json(flex(beef=False))
                        )
                    ]
                )
            )


            return

        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[
                    TemplateMessage(
                        alt_text='功能表',
                        template=ButtonsTemplate(
                            text='請選擇服務項目',
                            actions=[
                                PostbackAction(
                                    label='會員卡',
                                    displayText='顯示會員卡',
                                    data='action=member_card'
                                ),
                            ]
                        )
                    ),
                    TextMessage(text='請選擇你想吃什麼'),
                    FlexMessage(
                        alt_text='功能表',
                        contents=FlexCarousel.from_json(flex())
                    )
                ]
            )
        )


@handler.add(PostbackEvent)
def handle_postback(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        if event.postback.data == 'action=member_card':
            if os.path.exists('static/users.json'):
                users = json.load(open('static/users.json'))
            else:
                users = []

            userId = event.source.user_id
            user_info = list(filter(lambda x: x["id"] == userId, users))

            if len(user_info) == 0:
                user_info = {
                    "id": userId,
                    "name": "未提供",
                }
                users.append(user_info)
                with open("static/users.json", "w") as f:
                    json.dump(users, f)
            else:
                user_info = user_info[0]
            gen_member_card(user_info["name"], userId)
            uid = userId

            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        ImageMessage(
                            original_content_url=f"https://test-linebot.hsuan.app/static/card/{uid}.png",
                            preview_image_url=f"https://test-linebot.hsuan.app/static/card/{uid}.png"
                        ),
                        ImageMessage(
                            original_content_url=f"https://test-linebot.hsuan.app/static/card/{uid}_qr.png",
                            preview_image_url=f"https://test-linebot.hsuan.app/static/card/{uid}_qr.png"
                        )
                    ]
                )
            )


def gen_member_card(name, uid):
    # Open an Image
    img = Image.open("static/card.png")

    if not os.path.exists("static/card"):
        os.makedirs("static/card")

    qr = qrcode.make(uid, border=1)
    qr.save(f"static/card/{uid}_qr.png")

    barcode = Code128(uid[1:].zfill(12), writer=ImageWriter())
    barcode.save(f"static/card/{uid}_barcode")

    avatar_path = f"static/avatar/{uid}"
    if os.path.exists(avatar_path):
        avatar = Image.open(f"static/avatar/{uid}", formats=["png", "jpeg"])
    else:
        avatar = Image.open("static/avatar/default.png")
    base_width = 800
    wpercent = (base_width / float(avatar.size[0]))
    hsize = int((float(avatar.size[1]) * float(wpercent)))
    avatar = avatar.resize((800, hsize))
    img.paste(avatar, (300, 600))

    # Call draw Method to add 2D graphics in an image
    I1 = ImageDraw.Draw(img)
    # Add Text to an image
    I1.text((1800, 860), name, fill=(0, 0, 0), font=ImageFont.truetype('static/font.ttf', 64))
    I1.text((1800, 980), uid, fill=(0, 0, 0), font=ImageFont.truetype('static/font.ttf', 64))
    I1.text((1800, 1100), "綠星會員", fill=(0, 0, 0), font=ImageFont.truetype('static/font.ttf', 64))

    # Resize the QR code
    qr = qr.resize((400, 400))
    # Paste the QR code into the image
    img.paste(qr, (2400, 1300))

    barcode = Image.open(f"static/card/{uid}_barcode.png")
    img.paste(barcode, (1250, 1300))

    # Save the edited image
    img.save(f"static/card/{uid}.png")


@app.get('/api/admin/items')
def item_api_index():
    if not os.path.exists("static/item.json"):
        with open("static/item.json", "w") as f:
            f.write("[]")

    items = json.load(open("static/item.json"))
    return jsonify(items)


@app.get('/profile')
def profile():
    return render_template('profile.html')


@app.post('/api/admin/orders')
def order_api_create():
    if not os.path.exists("static/order.json"):
        with open("static/order.json", "w") as f:
            f.write("[]")

    if not os.path.exists("static/point.json"):
        with open("static/point.json", "w") as f:
            f.write("[]")

    orders = json.load(open("static/order.json"))
    points = json.load(open("static/point.json"))

    order_id = str(uuid4())
    orders.append({
        "id": order_id,
        "user_id": request.json["userId"],
        "items": request.json["items"],
        "total": request.json["total"],
    })

    point_record_id = str(uuid4())
    points.append({
        "id": point_record_id,
        "user_id": request.json["userId"],
        "description": f"消費 {request.json['total']} 元，獲得 {floor(request.json['total'] / 10)} 點",
        "order_id": order_id,
        "point": floor(request.json["total"] / 10),
        "created_at": datetime.now().isoformat(),
    })

    with open("static/order.json", "w") as f:
        json.dump(orders, f)

    with open("static/point.json", "w") as f:
        json.dump(points, f)

    return jsonify(orders)


@app.get('/api/admin/orders')
def order_api_index():
    if not os.path.exists("static/order.json"):
        with open("static/order.json", "w") as f:
            f.write("[]")

    orders = json.load(open("static/order.json"))
    items = json.load(open("static/item.json"))

    # inner join name, price
    for order in orders:
        order["items"] = list(map(lambda x: {
            "id": x["id"],
            "qty": x["qty"],
            "name": filter(lambda z: z["id"] == x["id"], items).__next__()["name"],
            "price": filter(lambda z: z["id"] == x["id"], items).__next__()["price"],
        }, order["items"]))

    # for order in orders:
    #     order["items"] = json.load(open("static/item.json"))
    #     order["items"] = list(filter(lambda x: x["id"] in order["items"], order["items"]))

    return jsonify(orders)


@app.post('/admin/items')
def item_create():
    if not os.path.exists("static/item.json"):
        with open("static/item.json", "w") as f:
            f.write("[]")

    items = json.load(open("static/item.json"))
    item_id = str(uuid4())

    request.files["image"].save(f"static/item/{item_id}.png")

    items.append({
        "id": item_id,
        "name": request.form["name"],
        "image": f"https://test-linebot.hsuan.app/static/item/{item_id}.png",
        "price": request.form["price"],
    })

    with open("static/item.json", "w") as f:
        json.dump(items, f)

    return redirect("https://test-linebot.hsuan.app/admin/items")


@app.get('/api/points')
def point_index():
    if not os.path.exists("static/point.json"):
        with open("static/point.json", "w") as f:
            f.write("[]")

    if not os.path.exists("static/users.json"):
        with open("static/users.json", "w") as f:
            f.write("[]")

    points = json.load(open("static/point.json"))
    users = json.load(open("static/users.json"))

    userId = request.headers.get("Authorization")
    userId = userId.replace("Bearer ", "")
    user_info = requests.post("https://api.line.me/oauth2/v2.1/verify", data={
        "id_token": userId,
        "client_id": os.environ.get("LINE_CHANNEL_ID"),
    }).json()
    userId = user_info["sub"]

    user_db_info = list(filter(lambda x: x["id"] == userId, users))
    if len(user_db_info) == 0:
        users.append({
            "id": userId,
            "name": user_info["name"],
        })
        with open("static/users.json", "w") as f:
            json.dump(users, f)

    points = list(filter(lambda x: x["user_id"] == userId, points))

    return jsonify(points)


@app.post('/profile/avatar')
def upload_avatar():
    if not os.path.exists("static/avatar"):
        os.makedirs("static/avatar")

    if not os.path.exists("static/users.json"):
        with open("static/users.json", "w") as f:
            f.write("[]")

    users = json.load(open("static/users.json"))

    userId = request.form.get('token')
    user_info = requests.post("https://api.line.me/oauth2/v2.1/verify", data={
        "id_token": userId,
        "client_id": os.environ.get("LINE_CHANNEL_ID"),
    }).json()
    print(user_info)
    userId = user_info["sub"]

    user_db = list(filter(lambda x: x["id"] == userId, users))
    if len(user_db) == 0:
        user_info = {
            "id": userId,
            "name": user_info["name"],
        }
        users.append(user_info)
        with open("static/users.json", "w") as f:
            json.dump(users, f)
    else:
        user_info = user_db[0]

    request.files["avatar"].save(f"static/avatar/{userId}")
    gen_member_card(user_info["name"], userId)
    return redirect("https://test-linebot.hsuan.app/")


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/admin')
def admin():
    return render_template('admin.html')


@app.get('/admin/items')
def item_index():
    return render_template('manage/items.html')


if __name__ == "__main__":
    app.run()
