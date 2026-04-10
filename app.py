# app.py - исправленная версия

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os, uuid
from functools import wraps
from werkzeug.utils import secure_filename
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secure_2026')

# Настройка логов для отладки
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

database_url = os.environ.get('DATABASE_URL', '')
if not database_url:
    logger.error("DATABASE_URL not set!")
    raise Exception("DATABASE_URL environment variable is required on Vercel")

if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://')

# Оптимизированные настройки для Vercel serverless
app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 1,  # Уменьшаем для serverless
        'max_overflow': 0,
        'pool_timeout': 30,
    },
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    # ВАЖНО: Vercel позволяет писать в /tmp, но данные не сохраняются между запросами
    UPLOAD_FOLDER='/tmp/uploads',
    # Отключаем сессии на файлах
    SESSION_TYPE='null',
)

# Создаем папку для загрузок при старте
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
DEFAULT_IMAGE = "default.png"

db = SQLAlchemy(app)

# Убираем дублирующийся teardown_request
@app.teardown_appcontext
def shutdown_session(exception=None):
    if exception:
        db.session.rollback()
    db.session.remove()

# ... (оставьте модели Product, Order, OrderItem без изменений) ...

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# Инициализация БД с обработкой ошибок
with app.app_context():
    try:
        db.create_all()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")

# ... (остальные маршруты остаются теми же, но добавьте логирование) ...

@app.route('/')
def index():
    try:
        products = Product.query.limit(8).all()
        return render_template('index.html', products=products)
    except Exception as e:
        logger.error(f"Index error: {str(e)}")
        return render_template('index.html', products=[]), 500

# ВАЖНО: Маршрут для загрузки изображений должен использовать /tmp
@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    # Проверяем, существует ли файл
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        # Возвращаем заглушку вместо 404
        return send_from_directory('static', 'default.png')
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Обработчик ошибок для Vercel
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {str(error)}")
    return "Internal server error", 500

# Исправленный маршрут добавления товара
@app.route('/admin/product/add', methods=['GET', 'POST'])
@login_required
def admin_product_add():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            category = request.form.get('category')
            price = float(request.form.get('price'))
            stock = int(request.form.get('stock', 0))
            description = request.form.get('description')
            image = request.files.get('image')
            image_filename = DEFAULT_IMAGE
            
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                ext = filename.rsplit('.', 1)[1].lower()
                unique_filename = f"{uuid.uuid4().hex}.{ext}"
                # Сохраняем в /tmp/uploads
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                image.save(save_path)
                logger.info(f"Image saved to {save_path}")
                image_filename = unique_filename
            
            product = Product(
                name=name, 
                category=category, 
                price=price, 
                stock=stock, 
                description=description, 
                image=image_filename
            )
            db.session.add(product)
            db.session.commit()
            flash('Товар добавлен', 'success')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Product add error: {str(e)}")
            flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('admin'))
    return render_template('product_form.html', title='Добавить товар', product=None)

# Остальные маршруты оставляем без изменений...

# Для Vercel обязательно использовать application
application = app

if __name__ == '__main__':
    app.run(debug=False)
