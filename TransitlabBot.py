import logging
import os
from datetime import datetime
import psycopg2
from psycopg2 import extras
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import gpxpy
from shapely.geometry import Point, LineString
from simplification.cutil import simplify_coords_vw
import pandas as pd
from sqlalchemy import create_engine
import itertools
import boto3

# Load environment variables
load_dotenv()

# Database connection
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_name = os.getenv('DB_NAME')

conn = psycopg2.connect(
    host=db_host,
    port=db_port,
    user=db_user,
    password=db_password,
    dbname=db_name
)

engine = create_engine(f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}')
# Configure S3
# s3_client = boto3.client('s3')
# s3_bucket_name = ''

# Read the token from the environment variable
TOKEN = os.getenv('BOT_TOKEN')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Global variables
user_data = {}
video_path = os.path.join(os.path.dirname(__file__), 'intro_480p.mp4')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🚌 تسجيل مسار الباص", callback_data='record_bus_route')],
        [InlineKeyboardButton("🚏 تسجيل محطة انطلاق الخط", callback_data='record_bus_stop')],
        [InlineKeyboardButton("🎥 مشاهدة فيديو تعريفي", callback_data='show_video')],
        [InlineKeyboardButton("❓ مساعدة", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_message = (
        "👋 <b>أهلاً بكم في بوت جامع البيانات!</b>\n"
        "شنو راح تسوي هسة؟"
    )
    await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')

async def show_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if os.path.exists(video_path):
        with open(video_path, 'rb') as video_file:
            await context.bot.send_video(chat_id=query.message.chat_id, video=video_file, caption=" للعودة إلى القائمة الرئيسية اضغط /start")
    else:
        await context.bot.send_message(chat_id=query.message.chat_id, text="الفيديو غير موجود. يرجى المحاولة لاحقاً.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "❓ مساعدة:\n"
        "1. <b>🚌 تسجيل مسار الباص:</b> تسجيل مسار الباص بواسطة برنامج تسجيل المسار باستخدام GPS حيث يتم تسجيل المسار للباص عند الصعود وانهاء التسجيل عند النزول ثم ارسال ملف التتبع الى البوت لحفظ المعلومات.\n"
        "2. <b>🚏 تسجيل محطة انطلاق الخط:</b> يستخدم هذا الخيار لتسجيل موقع انطلاق الباص من الكراج او من اماكن تجمع الباصات."
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    logging.info(f"Button pressed: {query.data} by user {user_id}")

    if query.data == 'show_video':
        await show_video(update, context)
        return

    if query.data == 'record_bus_route':
        user_data[user_id] = {'step': 'phone_type', 'username': query.from_user.username, 'session_id': datetime.now().strftime("%Y%m%d%H%M%S")}
        keyboard = [
            [InlineKeyboardButton("📱 iPhone", callback_data='phone_iphone')],
            [InlineKeyboardButton("📱 Android", callback_data='phone_android')],
            [InlineKeyboardButton("✅ لقد قمت بتثبيت التطبيق", callback_data='phone_installed')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "لتسجيل مسار الباص يجب تنصيب برنامج التتبع وتشغيله. وبعدها ارسال ملف التتبع الى البوت لحفظ المعلومات.\n<b>شنو نوع الموبايل اللي تستخدمه؟</b>",
            reply_markup=reply_markup, parse_mode='HTML'
        )

    elif query.data in ['phone_iphone', 'phone_android']:
        keyboard = [
            [InlineKeyboardButton("✅ تم", callback_data='phone_installed')],
            [InlineKeyboardButton("❌ إلغاء", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        app_link = "https://apps.apple.com/app/id984503772" if query.data == 'phone_iphone' else "https://play.google.com/store/apps/details?id=com.ilyabogdanovich.geotracker"
        await query.edit_message_text(f"يرجى تثبيت التطبيق من الرابط التالي:\n{app_link}", reply_markup=reply_markup)

    elif query.data == 'phone_installed':
        user_data[user_id]['step'] = 'upload_gpx'
        await query.edit_message_text("📂  ابدا بتسجيل الرحلة من التطبيق ولا تنسى تسجيل نقطة عند ركوب او خروج اي راكب اذا امكن . وعند الانتهاء يرجى إرسال ملف GPX الخاص بالمسار الذي سجلته باستخدام تطبيق التتبع.")

    elif query.data == 'record_bus_stop':
        user_data[user_id] = {'step': 'vehicle_type_stop', 'session_id': datetime.now().strftime("%Y%m%d%H%M%S"), 'username': query.from_user.username}
        keyboard = [
            [InlineKeyboardButton("🚐 كيا", callback_data='vehicle_kia_stop')],
            [InlineKeyboardButton("🚍 كوستر", callback_data='vehicle_coaster_stop')],
            [InlineKeyboardButton("🚌 باص", callback_data='vehicle_bus_stop')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("شنو نوع النقل العام اللي راح تستخدمه؟", reply_markup=reply_markup)

    elif query.data == 'help':
        await help_command(query, context)

    elif query.data == 'cancel':
        user_data[user_id]['last_step'] = user_data[user_id]['step']  # Store the current step
        keyboard = [
            [InlineKeyboardButton("✅ نعم", callback_data='confirm_cancel')],
            [InlineKeyboardButton("❌ لا", callback_data='deny_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("❌ هل أنت متأكد من الإلغاء؟", reply_markup=reply_markup)

    elif query.data == 'confirm_cancel':
        await mark_session_as_canceled(user_id)
        user_data.pop(user_id, None)
        await query.edit_message_text("تم الإلغاء! يرجى الضغط على /start للعودة إلى القائمة الرئيسية.", reply_markup=InlineKeyboardMarkup([]))

    elif query.data == 'deny_cancel':
        # Resume from the last step
        if user_id in user_data and 'last_step' in user_data[user_id]:
            step = user_data[user_id]['last_step']
            if step == 'upload_gpx':
                await query.edit_message_text("📂  ابدا بتسجيل الرحلة من التطبيق ولا تنسى تسجيل نقطة عند ركوب او خروج اي راكب اذا امكن . وعند الانتهاء يرجى إرسال ملف GPX الخاص بالمسار الذي سجلته باستخدام تطبيق التتبع.")
            elif step == 'vehicle_type':
                keyboard = [
                    [InlineKeyboardButton("🚐 كيا", callback_data='vehicle_kia')],
                    [InlineKeyboardButton("🚍 كوستر", callback_data='vehicle_coaster')],
                    [InlineKeyboardButton("🚌 باص", callback_data='vehicle_bus')],
                    [InlineKeyboardButton("❌ إلغاء", callback_data='cancel')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("شنو نوع النقل العام اللي راح تستخدمه؟", reply_markup=reply_markup)
            elif step == 'source':
                await query.edit_message_text("🗺️ أدخل مكان الانطلاق (من وين طالع الباص؟ مثلا علاوي, باب معظم, بياع .. الخ):")
            elif step == 'destination':
                await query.edit_message_text("🗺️ أدخل الوجهة (ليوين رايح الباص؟):")
            elif step == 'enter_fare':
                await query.edit_message_text("💬 أدخل الأجرة يدويًا (ارقام فقط بدون العملة):")
            elif step == 'vehicle_type_stop':
                keyboard = [
                    [InlineKeyboardButton("🚐 كيا", callback_data='vehicle_kia_stop')],
                    [InlineKeyboardButton("🚍 كوستر", callback_data='vehicle_coaster_stop')],
                    [InlineKeyboardButton("🚌 باص", callback_data='vehicle_bus_stop')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("شنو نوع النقل العام اللي راح تستخدمه؟", reply_markup=reply_markup)
            elif step == 'destination_bus_stop':
                await query.edit_message_text("🗺️ أدخل الوجهة (ليوين رايح الباص؟):")
            # Restore the original step
            user_data[user_id]['step'] = user_data[user_id].pop('last_step')

    elif query.data.startswith('fare_'):
        if user_id not in user_data:
            logging.error(f"Missing user data for user {user_id} when selecting fare")
            return
        fare = query.data.split('_')[1]
        if fare == 'other':
            user_data[user_id]['step'] = 'enter_fare'
            await query.edit_message_text("💬 أدخل الأجرة يدويًا (ارقام فقط بدون العملة):")
        else:
            user_data[user_id]['fare'] = fare
            await ask_vehicle_condition(user_id, context)

    elif query.data.startswith('condition_'):
        vehicle_condition = query.data.split('condition_')[1]
        if user_id in user_data and 'fare' in user_data[user_id] and 'session_id' in user_data[user_id]:
            user_data[user_id]['vehicle_condition'] = vehicle_condition
            await save_all_data(user_id)
            await query.edit_message_text("تم تسجيل الأجرة وحالة المركبة. شكراً! اضغط /start للعودة إلى القائمة الرئيسية.", reply_markup=InlineKeyboardMarkup([]))
        else:
            logging.error(f"Missing session data for user {user_id}")

    elif query.data in ['vehicle_kia', 'vehicle_coaster', 'vehicle_bus']:
        vehicle_type = query.data.split('_')[1]
        user_data[user_id]['vehicle_type'] = vehicle_type.capitalize()
        user_data[user_id]['step'] = 'source'
        await query.edit_message_text("🗺️ أدخل مكان الانطلاق (من وين طالع الباص؟ مثلا علاوي, باب معظم, بياع .. الخ):")

    elif query.data in ['vehicle_kia_stop', 'vehicle_coaster_stop', 'vehicle_bus_stop']:
        vehicle_type = query.data.split('_')[1]
        user_data[user_id]['vehicle_type'] = vehicle_type.capitalize()
        user_data[user_id]['step'] = 'destination_bus_stop'
        await query.edit_message_text("🗺️ أدخل الوجهة (ليوين رايح الباص؟):")

async def ask_vehicle_condition(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("😡 سيئة جداً", callback_data='condition_very_bad')],
        [InlineKeyboardButton("😟 سيئة", callback_data='condition_bad')],
        [InlineKeyboardButton("🙂 جيدة", callback_data='condition_good')],
        [InlineKeyboardButton("😃 جيدة جداً", callback_data='condition_very_good')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=user_id, text="🚐 كيف كانت حالة المركبة (شنو تقييمك للسيارة بشكل عام)؟", reply_markup=reply_markup)

async def mark_session_as_canceled(user_id: int) -> None:
    logging.info(f"Marking session as canceled for user {user_id}")
    session_id = user_data[user_id]['session_id']
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE bus_routes
            SET cancel = TRUE
            WHERE user_id = %s AND session_id = %s
            """, (user_id, session_id)
        )
        conn.commit()

async def save_fare(user_id: int) -> None:
    try:
        current_time = datetime.now()
        session_id = user_data[user_id]['session_id']
        username = user_data[user_id]['username']
        source = user_data[user_id].get('source', 'unknown')
        destination = user_data[user_id].get('destination', 'unknown')
        fare = user_data[user_id]['fare']
        vehicle_condition = user_data[user_id]['vehicle_condition']
        vehicle_type = user_data[user_id]['vehicle_type']

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fares (user_id, telegram_username, session_id, date, time, source, destination, fare, vehicle_condition, vehicle_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, username, session_id, current_time.date(), current_time.time(), source, destination, fare, vehicle_condition, vehicle_type)
            )
            conn.commit()
        logging.info("Fare data saved to the database")
    except Exception as e:
        conn.rollback()  # Rollback the transaction in case of error
        logging.error(f"Error saving fare data: {e}")

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    text = update.message.text

    logging.info(f"User choice: {text} by user {user_id}")

    if user_id not in user_data:
        user_data[user_id] = {'session_id': datetime.now().strftime("%Y%m%d%H%M%S"), 'username': update.message.from_user.username}

    if user_id in user_data and user_data[user_id]['step'] == 'source':
        user_data[user_id]['source'] = text
        user_data[user_id]['step'] = 'destination'
        await update.message.reply_text("🗺️ أدخل الوجهة (ليوين رايح الباص؟):")

    elif user_id in user_data and user_data[user_id]['step'] == 'destination':
        user_data[user_id]['destination'] = text
        await ask_fare(user_id, context)

    elif user_data[user_id]['step'] == 'enter_fare':
        user_data[user_id]['fare'] = text
        await ask_vehicle_condition(user_id, context)

    elif user_id in user_data and user_data[user_id]['step'] == 'destination_bus_stop':
        user_data[user_id]['destination'] = text
        user_data[user_id]['step'] = 'location_bus_stop'
        keyboard = [
            [KeyboardButton("📍 مشاركة الموقع", request_location=True)],
            ["❌ إلغاء"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("يرجى مشاركة موقعك لحفظ محطة انطلاق الخط.", reply_markup=reply_markup)

    elif text == "❌ إلغاء":
        keyboard = [
            [InlineKeyboardButton("✅ نعم", callback_data='confirm_cancel')],
            [InlineKeyboardButton("❌ لا", callback_data='deny_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❌ هل أنت متأكد من الإلغاء؟", reply_markup=reply_markup)

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id not in user_data:
        await update.message.reply_text("يرجى الاختيار من القائمة.")
        return

    current_time = datetime.now()
    lat, lon = update.message.location.latitude, update.message.location.longitude

    if user_data[user_id].get('step') == 'location_bus_stop':
        session_id = user_data[user_id]['session_id']
        vehicle_type = user_data[user_id]['vehicle_type']
        username = user_data[user_id]['username']

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bus_stops (user_id, telegram_username, session_id, vehicle_type, date, time, destination, lat, lon, cancel)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, username, session_id, vehicle_type, current_time.date(), current_time.time(), user_data[user_id]['destination'], lat, lon, False)
            )
            conn.commit()

        user_data.pop(user_id, None)
        await update.message.reply_text("تم حفظ محطة انطلاق الخط. شكراً! اضغط /start للعودة للقائمة الرئيسية.", reply_markup=ReplyKeyboardRemove())

def chunked_iterable(iterable, size):
    it = iter(iterable)
    while chunk := list(itertools.islice(it, size)):
        yield chunk

def simplify_route(route_points, tolerance=0.000000001):
    line = LineString(route_points)
    simplified = simplify_coords_vw(line.coords, tolerance)
    return list(simplified)

def get_route_points(session_id, point_type):
    query = """
        SELECT lon, lat, time, telegram_username, date, source, destination, cancel
        FROM bus_routes
        WHERE session_id = %s AND point_type = %s
        ORDER BY time
    """
    df = pd.read_sql(query, engine, params=(session_id, point_type))
    return df

def save_to_simplified_table(user_id, username, vehicle_type, session_id, source, destination, simplified_points):
    logging.info("Inside save_to_simplified_table")
    line_geom = LineString(simplified_points).wkt

    single_row = (
        session_id,
        user_id,
        username,
        vehicle_type,
        datetime.now().date(),
        datetime.now().time(),
        source,
        destination,
        False,
        line_geom
    )

    insert_query = """
        INSERT INTO simplified_bus_routes (session_id, user_id, telegram_username, vehicle_type, date, time, source, destination, cancel, geom_line)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326))
    """

    with conn.cursor() as cur:
        cur.execute(insert_query, single_row)
        conn.commit()

    logging.info("Exiting save_to_simplified_table")

async def gpx_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id not in user_data or user_data[user_id].get('step') != 'upload_gpx':
        await update.message.reply_text("يرجى الاختيار من القائمة.")
        return

    # Download the GPX file
    file = await context.bot.get_file(update.message.document.file_id)
    session_id = user_data[user_id]['session_id']
    username = user_data[user_id]['username']
    current_date = datetime.now().strftime("%Y%m%d")
    file_name = f'{username}_{session_id}_{current_date}.gpx'
    file_path = os.path.join(os.getcwd(), file_name)
    await file.download_to_drive(file_path)

    try:
        # Upload the file to S3
        s3_key = f'gpx-files/{file_name}'
        s3_client.upload_file(file_path, s3_bucket_name, s3_key)
        logging.info(f"GPX file uploaded to S3 at {s3_key}")
    except Exception as e:
        logging.error(f"Error uploading to s3: {e}")

    try:
        # Initialize gpx_data dictionary
        user_data[user_id]['gpx_data'] = {
            'tracks': [],
            'waypoints': []
        }

        # Parse the GPX file
        with open(file_path, 'r') as gpx_file:
            gpx = gpxpy.parse(gpx_file)

        logging.info("GPX file parsed successfully")

        point_id = 1

        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    user_data[user_id]['gpx_data']['tracks'].append({
                        'lat': point.latitude,
                        'lon': point.longitude,
                        'time': point.time,
                        'type': 'bus_routing'
                    })
                    point_id += 1

        point_id = 1
        for waypoint in gpx.waypoints:
            user_data[user_id]['gpx_data']['waypoints'].append({
                'lat': waypoint.latitude,
                'lon': waypoint.longitude,
                'time': waypoint.time,
                'type': 'passenger_on_off'
            })
            point_id += 1

        await ask_vehicle_type(user_id, context)
    except Exception as e:
        logging.error(f"Error processing GPX file: {e}")
        await update.message.reply_text("حدث خطأ أثناء معالجة ملف GPX. يرجى المحاولة مرة أخرى.")

async def ask_fare(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("💵 250", callback_data='fare_250'),
            InlineKeyboardButton("💵 500", callback_data='fare_500')
        ],
        [
            InlineKeyboardButton("💵 750", callback_data='fare_750'),
            InlineKeyboardButton("💵 1000", callback_data='fare_1000')
        ],
        [
            InlineKeyboardButton("💵 1250", callback_data='fare_1250'),
            InlineKeyboardButton("💵 1500", callback_data='fare_1500')
        ],
        [
            InlineKeyboardButton("💵 2000", callback_data='fare_2000'),
            InlineKeyboardButton("💬 أخرى", callback_data='fare_other')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=user_id, text="💵 كم كانت الأجرة؟", reply_markup=reply_markup)

async def ask_vehicle_type(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🚐 كيا", callback_data='vehicle_kia')],
        [InlineKeyboardButton("🚍 كوستر", callback_data='vehicle_coaster')],
        [InlineKeyboardButton("🚌 باص", callback_data='vehicle_bus')],
        [InlineKeyboardButton("❌ إلغاء", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=user_id, text="شنو نوع النقل العام اللي راح تستخدمه؟", reply_markup=reply_markup)

async def save_all_data(user_id: int) -> None:
    try:
        if 'source' not in user_data[user_id] or 'destination' not in user_data[user_id] or 'vehicle_type' not in user_data[user_id]:
            logging.info("Not all necessary data is available yet. Waiting for user input.")
            return
        session_id = user_data[user_id]['session_id']
        username = user_data[user_id]['username']
        source = user_data[user_id].get('source', 'unknown')
        destination = user_data[user_id].get('destination', 'unknown')
        vehicle_type = user_data[user_id]['vehicle_type']
        fare = user_data[user_id]['fare']
        vehicle_condition = user_data[user_id]['vehicle_condition']

        tracks = user_data[user_id]['gpx_data']['tracks']
        waypoints = user_data[user_id]['gpx_data']['waypoints']

        with conn.cursor() as cur:
            track_values = [
                (
                    user_id, username, session_id, vehicle_type, point_id,
                    track['time'].date(), track['time'].time(), source, destination,
                    track['lat'], track['lon'], 'bus_routing', False
                ) for point_id, track in enumerate(tracks, start=1)
            ]

            waypoint_values = [
                (
                    user_id, username, session_id, vehicle_type, point_id,
                    waypoint['time'].date(), waypoint['time'].time(), source, destination,
                    waypoint['lat'], waypoint['lon'], 'passenger_on_off', False
                ) for point_id, waypoint in enumerate(waypoints, start=1)
            ]

            sql_query = """
                INSERT INTO bus_routes (user_id, telegram_username, session_id, vehicle_type, point_id, date, time, source, destination, lat, lon, point_type, cancel)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            extras.execute_batch(cur, sql_query, track_values + waypoint_values)

            cur.execute(
                """
                INSERT INTO fares (user_id, telegram_username, session_id, date, time, source, destination, fare, vehicle_condition, vehicle_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, username, session_id, datetime.now().date(), datetime.now().time(), source, destination, fare, vehicle_condition, vehicle_type)
            )

            conn.commit()

        track_update_values = [
            (Point(track['lon'], track['lat']).wkt, session_id, track['lat'], track['lon'])
            for track in tracks
        ]
        waypoint_update_values = [
            (Point(waypoint['lon'], waypoint['lat']).wkt, session_id, waypoint['lat'], waypoint['lon'])
            for waypoint in waypoints
        ]

        track_update_query = """
            UPDATE bus_routes
            SET geom_point = ST_SetSRID(ST_GeomFromText(%s), 4326)
            WHERE session_id = %s AND point_type = 'bus_routing' AND lat = %s AND lon = %s
        """
        waypoint_update_query = """
            UPDATE bus_routes
            SET geom_point = ST_SetSRID(ST_GeomFromText(%s), 4326)
            WHERE session_id = %s AND point_type = 'passenger_on_off' AND lat = %s AND lon = %s
        """

        with conn.cursor() as cur:
            extras.execute_batch(cur, track_update_query, track_update_values)
            extras.execute_batch(cur, waypoint_update_query, waypoint_update_values)
            conn.commit()

        df = get_route_points(session_id, 'bus_routing')
        route_points = list(zip(df['lon'], df['lat']))
        simplified_points = simplify_route(route_points)
        logging.info("Calling save_to_simplified_table...")
        save_to_simplified_table(user_id, username, vehicle_type, session_id, source, destination, simplified_points)
        logging.info("save_to_simplified_table called successfully")
        logging.info("All data saved to the database")
    except Exception as e:
        conn.rollback()
        logging.error(f"Error saving all data: {e}")


def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice))
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))
    application.add_handler(MessageHandler(filters.Document.FileExtension("gpx"), gpx_handler))

    logging.getLogger('httpx').setLevel(logging.WARNING)

    application.run_polling()

if __name__ == '__main__':
    main()
