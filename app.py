"""智汇优品 — 网络应用架构课程设计 主应用"""
import os
import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, session, abort)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from flask_mail import Mail, Message
from sqlalchemy import func, desc, and_

from config import Config
from models import (db, User, Category, Product, CartItem, Order, OrderItem,
                    BrowseLog, PurchaseLog, LoginLog, OperationLog)


# ── 应用工厂 ───────────────────────────────────────────
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


app = create_app()
mail = Mail(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录后再访问此页面。'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── 装饰器 ─────────────────────────────────────────────
def role_required(*roles):
    """角色权限装饰器"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.role not in roles:
                flash('您没有权限访问此页面。', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def log_operation(action):
    """记录操作日志"""
    try:
        log = OperationLog(
            user_id=current_user.id,
            action=action,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass


# ── 上下文处理器 ───────────────────────────────────────
@app.context_processor
def inject_globals():
    categories = Category.query.order_by(Category.name).all()
    cart_count = 0
    if current_user.is_authenticated:
        cart_count = CartItem.query.filter_by(user_id=current_user.id).count()
    return dict(categories=categories, cart_count=cart_count)


# ═══════════════════════════════════════════════════════
#  首页 & 商品浏览
# ═══════════════════════════════════════════════════════

@app.route('/')
def index():
    """首页 — 展示商品列表、排行榜、推荐"""
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category', type=int)
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'default')

    query = Product.query.filter_by(is_active=True)

    if category_id:
        query = query.filter_by(category_id=category_id)

    if search:
        query = query.filter(
            db.or_(Product.name.contains(search),
                   Product.description.contains(search))
        )

    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort == 'sales':
        query = query.order_by(Product.sales_count.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.paginate(page=page, per_page=app.config['ITEMS_PER_PAGE'], error_out=False)

    # 销售排行榜 TOP 10
    top_products = Product.query.filter_by(is_active=True).order_by(
        Product.sales_count.desc()).limit(10).all()

    # 推荐：如果用户已登录，推荐其偏好类别商品
    recommended = []
    if current_user.is_authenticated and current_user.preferred_category:
        cat = Category.query.filter_by(name=current_user.preferred_category).first()
        if cat:
            recommended = Product.query.filter_by(
                category_id=cat.id, is_active=True
            ).order_by(Product.sales_count.desc()).limit(6).all()

    return render_template('index.html', products=products,
                           top_products=top_products,
                           recommended=recommended,
                           current_category=category_id,
                           search=search, sort=sort)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """商品详情页 — 含浏览行为记录"""
    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        flash('商品不存在或已下架。', 'warning')
        return redirect(url_for('index'))

    # 记录浏览行为
    user_id = current_user.id if current_user.is_authenticated else None
    log = BrowseLog(
        user_id=user_id,
        product_id=product.id,
        category_id=product.category_id,
        ip_address=request.remote_addr,
        duration_seconds=0
    )
    db.session.add(log)
    db.session.commit()

    # 协同过滤："浏览过此商品的人也买了..."
    also_bought = _get_also_bought(product_id)

    return render_template('product_detail.html', product=product,
                           also_bought=also_bought)


def _get_also_bought(product_id, limit=6):
    """协同过滤：找到购买了当前商品的用户还买了什么"""
    # 找到购买过此商品的用户
    buyer_ids = db.session.query(PurchaseLog.user_id).filter(
        PurchaseLog.product_id == product_id
    ).distinct().subquery()

    # 这些用户还买了什么其他商品
    other_products = db.session.query(
        PurchaseLog.product_id,
        func.count(PurchaseLog.id).label('cnt')
    ).filter(
        PurchaseLog.user_id.in_(buyer_ids),
        PurchaseLog.product_id != product_id
    ).group_by(PurchaseLog.product_id).order_by(
        desc('cnt')
    ).limit(limit).all()

    result = []
    for pid, cnt in other_products:
        p = db.session.get(Product, pid)
        if p and p.is_active:
            result.append(p)
    return result


# ═══════════════════════════════════════════════════════
#  用户认证系统
# ═══════════════════════════════════════════════════════

@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')
        region = request.form.get('region', '').strip()

        if not username or not email or not password:
            flash('请填写所有必填字段。', 'danger')
            return render_template('register.html')

        if password != confirm:
            flash('两次输入的密码不一致。', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('密码长度不能少于6位。', 'danger')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash('用户名已存在。', 'danger')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('该邮箱已被注册。', 'danger')
            return render_template('register.html')

        user = User(username=username, email=email, region=region)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('注册成功！请登录。', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录 — 含登录日志记录"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash('用户名或密码错误。', 'danger')
            return render_template('login.html')

        if not user.is_active:
            flash('该账号已被禁用。', 'danger')
            return render_template('login.html')

        login_user(user, remember=remember)

        # 记录登录日志
        log = LoginLog(
            user_id=user.id,
            ip_address=request.remote_addr
        )
        db.session.add(log)

        # 销售人员/管理员记录操作日志
        if user.role in ('sales', 'admin'):
            oplog = OperationLog(
                user_id=user.id,
                action=f'登录系统',
                ip_address=request.remote_addr
            )
            db.session.add(oplog)

        db.session.commit()

        flash(f'欢迎回来，{user.username}！', 'success')

        # 根据角色跳转
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        if user.is_admin():
            return redirect(url_for('admin_dashboard'))
        elif user.is_sales():
            return redirect(url_for('sales_dashboard'))
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功退出登录。', 'info')
    return redirect(url_for('index'))


# ═══════════════════════════════════════════════════════
#  购物车
# ═══════════════════════════════════════════════════════

@app.route('/cart')
@login_required
def cart():
    """查看购物车"""
    items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(item.product.price * item.quantity for item in items if item.product and item.product.is_active)
    return render_template('cart.html', items=items, total=total)


@app.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def cart_add(product_id):
    """添加商品到购物车"""
    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        flash('商品不存在。', 'danger')
        return redirect(url_for('index'))

    quantity = int(request.form.get('quantity', 1))
    if quantity > product.stock:
        flash(f'库存不足，当前仅剩 {product.stock} 件。', 'warning')
        return redirect(url_for('product_detail', product_id=product_id))

    item = CartItem.query.filter_by(
        user_id=current_user.id, product_id=product_id
    ).first()

    if item:
        item.quantity += quantity
    else:
        item = CartItem(user_id=current_user.id, product_id=product_id, quantity=quantity)
        db.session.add(item)

    db.session.commit()
    flash(f'"{product.name}" 已添加到购物车。', 'success')
    return redirect(url_for('cart'))


@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def cart_update(item_id):
    """更新购物车商品数量"""
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)
    quantity = int(request.form.get('quantity', 1))
    if quantity <= 0:
        db.session.delete(item)
    else:
        item.quantity = min(quantity, item.product.stock)
    db.session.commit()
    return redirect(url_for('cart'))


@app.route('/cart/remove/<int:item_id>')
@login_required
def cart_remove(item_id):
    """从购物车移除商品"""
    item = CartItem.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        abort(403)
    db.session.delete(item)
    db.session.commit()
    flash('商品已从购物车移除。', 'info')
    return redirect(url_for('cart'))


# ═══════════════════════════════════════════════════════
#  订单系统
# ═══════════════════════════════════════════════════════

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """结算下单"""
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('购物车为空，请先添加商品。', 'warning')
        return redirect(url_for('cart'))

    # 过滤无效商品
    valid_items = [item for item in cart_items if item.product and item.product.is_active]
    if not valid_items:
        flash('购物车中的商品均已下架。', 'warning')
        return redirect(url_for('cart'))

    if request.method == 'POST':
        # 创建订单
        total = sum(item.product.price * item.quantity for item in valid_items)
        order = Order(user_id=current_user.id, total_amount=total, status='paid')
        db.session.add(order)
        db.session.flush()  # 获取 order.id

        for item in valid_items:
            product = item.product
            # 检查库存
            if item.quantity > product.stock:
                flash(f'"{product.name}" 库存不足，请调整数量。', 'danger')
                db.session.rollback()
                return redirect(url_for('cart'))

            # 创建订单项
            oi = OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                price=product.price,
                quantity=item.quantity
            )
            db.session.add(oi)

            # 更新库存和销量
            product.stock -= item.quantity
            product.sales_count += item.quantity

            # 记录购买日志
            plog = PurchaseLog(
                user_id=current_user.id,
                product_id=product.id,
                category_id=product.category_id,
                quantity=item.quantity,
                unit_price=product.price,
                total_price=product.price * item.quantity
            )
            db.session.add(plog)

        # 清空购物车
        CartItem.query.filter_by(user_id=current_user.id).delete()

        # 更新用户消费总额和偏好
        current_user.total_spent += total
        _update_user_preference(current_user)

        # 记录操作日志
        oplog = OperationLog(
            user_id=current_user.id,
            action=f'下单 #{order.id}，金额 ¥{total:.2f}',
            ip_address=request.remote_addr
        )
        db.session.add(oplog)

        db.session.commit()

        # 发送邮件确认（如果配置了邮件）
        _send_order_email(current_user, order)

        flash(f'订单 #{order.id} 已生成，支付成功！我们会尽快发货。', 'success')
        return redirect(url_for('order_detail', order_id=order.id))

    total = sum(item.product.price * item.quantity for item in valid_items)
    return render_template('checkout.html', items=valid_items, total=total)


def _update_user_preference(user):
    """根据购买记录更新用户偏好类别"""
    result = db.session.query(
        PurchaseLog.category_id,
        func.sum(PurchaseLog.total_price).label('total')
    ).filter_by(user_id=user.id).group_by(
        PurchaseLog.category_id
    ).order_by(desc('total')).first()

    if result:
        cat = db.session.get(Category, result[0])
        if cat:
            user.preferred_category = cat.name
            db.session.commit()


def _send_order_email(user, order):
    """发送订单确认邮件"""
    try:
        if app.config['MAIL_USERNAME']:
            msg = Message(
                f'智汇优品 - 订单确认 #{order.id}',
                sender=app.config['MAIL_USERNAME'],
                recipients=[user.email]
            )
            msg.body = f"""亲爱的 {user.username}：

您的订单 #{order.id} 已确认，订单金额 ¥{order.total_amount:.2f}。

感谢您的购买！

智汇优品
"""
            mail.send(msg)
    except Exception:
        pass  # 邮件发送失败不影响下单流程


@app.route('/orders')
@login_required
def order_list():
    """订单列表"""
    orders = Order.query.filter_by(user_id=current_user.id).order_by(
        Order.created_at.desc()).all()
    return render_template('orders.html', orders=orders)


@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    """订单详情"""
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and current_user.role not in ('sales', 'admin'):
        abort(403)
    return render_template('order_detail.html', order=order)


# ═══════════════════════════════════════════════════════
#  销售人员功能
# ═══════════════════════════════════════════════════════

@app.route('/sales')
@login_required
@role_required('sales', 'admin')
def sales_dashboard():
    """销售人员仪表盘"""
    # 商品统计
    total_products = Product.query.count()
    active_products = Product.query.filter_by(is_active=True).count()
    low_stock = Product.query.filter(Product.stock < 10, Product.is_active == True).count()

    # 订单统计
    total_orders = Order.query.count()
    today_orders = Order.query.filter(
        Order.created_at >= datetime.utcnow().date()
    ).count()
    total_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status != 'cancelled'
    ).scalar() or 0

    # 销售趋势（最近7天）
    sales_trend = _get_sales_trend(7)

    # 库存预警
    low_stock_products = Product.query.filter(
        Product.stock < 10, Product.is_active == True
    ).order_by(Product.stock).limit(10).all()

    return render_template('sales/dashboard.html',
                           total_products=total_products,
                           active_products=active_products,
                           low_stock=low_stock,
                           total_orders=total_orders,
                           today_orders=today_orders,
                           total_revenue=total_revenue,
                           sales_trend=sales_trend,
                           low_stock_products=low_stock_products)


@app.route('/sales/products')
@login_required
@role_required('sales', 'admin')
def sales_products():
    """商品管理列表"""
    page = request.args.get('page', 1, type=int)
    products = Product.query.order_by(Product.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)
    return render_template('sales/products.html', products=products)


@app.route('/sales/product/add', methods=['GET', 'POST'])
@login_required
@role_required('sales', 'admin')
def sales_product_add():
    """添加商品"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        price = float(request.form.get('price', 0))
        stock = int(request.form.get('stock', 0))
        category_id = int(request.form.get('category_id', 0))
        image_url = request.form.get('image_url', '').strip()

        if not name or price <= 0:
            flash('请填写商品名称和有效价格。', 'danger')
            return render_template('sales/product_form.html', product=None)

        product = Product(
            name=name, description=description, price=price,
            stock=stock, category_id=category_id if category_id else None,
            image_url=image_url
        )
        db.session.add(product)

        log_operation(f'添加商品: {name}')
        db.session.commit()

        flash(f'商品 "{name}" 添加成功。', 'success')
        return redirect(url_for('sales_products'))

    return render_template('sales/product_form.html', product=None)


@app.route('/sales/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@role_required('sales', 'admin')
def sales_product_edit(product_id):
    """编辑商品"""
    product = db.session.get(Product, product_id)
    if not product:
        flash('商品不存在。', 'danger')
        return redirect(url_for('sales_products'))

    if request.method == 'POST':
        product.name = request.form.get('name', '').strip()
        product.description = request.form.get('description', '').strip()
        product.price = float(request.form.get('price', 0))
        product.stock = int(request.form.get('stock', 0))
        product.category_id = int(request.form.get('category_id', 0)) or None
        product.image_url = request.form.get('image_url', '').strip()
        product.is_active = request.form.get('is_active') == 'on'

        log_operation(f'修改商品 #{product.id}: {product.name}')
        db.session.commit()

        flash(f'商品 "{product.name}" 已更新。', 'success')
        return redirect(url_for('sales_products'))

    return render_template('sales/product_form.html', product=product)


@app.route('/sales/product/delete/<int:product_id>', methods=['POST'])
@login_required
@role_required('sales', 'admin')
def sales_product_delete(product_id):
    """删除商品"""
    product = db.session.get(Product, product_id)
    if product:
        name = product.name
        product.is_active = False
        log_operation(f'下架商品: {name}')
        db.session.commit()
        flash(f'商品 "{name}" 已下架。', 'info')
    return redirect(url_for('sales_products'))


@app.route('/sales/categories', methods=['GET', 'POST'])
@login_required
@role_required('sales', 'admin')
def sales_categories():
    """商品类别管理"""
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name', '').strip()
            if name and not Category.query.filter_by(name=name).first():
                cat = Category(name=name)
                db.session.add(cat)
                log_operation(f'添加类别: {name}')
                db.session.commit()
                flash(f'类别 "{name}" 添加成功。', 'success')
        elif action == 'delete':
            cat_id = int(request.form.get('category_id', 0))
            cat = db.session.get(Category, cat_id)
            if cat:
                name = cat.name
                # 将该类别商品设为无类别
                Product.query.filter_by(category_id=cat.id).update({Product.category_id: None})
                db.session.delete(cat)
                log_operation(f'删除类别: {name}')
                db.session.commit()
                flash(f'类别 "{name}" 已删除。', 'info')

    categories = Category.query.order_by(Category.name).all()
    return render_template('sales/categories.html', categories=categories)


@app.route('/sales/logs')
@login_required
@role_required('sales', 'admin')
def sales_logs():
    """浏览/购买日志查看"""
    page = request.args.get('page', 1, type=int)
    log_type = request.args.get('type', 'browse')

    if log_type == 'purchase':
        logs = PurchaseLog.query.order_by(PurchaseLog.created_at.desc()).paginate(
            page=page, per_page=30, error_out=False)
    else:
        logs = BrowseLog.query.order_by(BrowseLog.created_at.desc()).paginate(
            page=page, per_page=30, error_out=False)

    return render_template('sales/logs.html', logs=logs, log_type=log_type)


# ═══════════════════════════════════════════════════════
#  管理员功能
# ═══════════════════════════════════════════════════════

@app.route('/admin')
@login_required
@role_required('admin')
def admin_dashboard():
    """管理员仪表盘"""
    user_count = User.query.count()
    product_count = Product.query.count()
    order_count = Order.query.count()
    total_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status != 'cancelled'
    ).scalar() or 0

    # 销售排行
    sales_ranking = db.session.query(
        Product.name, Product.sales_count
    ).filter(Product.is_active == True).order_by(
        Product.sales_count.desc()
    ).limit(10).all()

    # 销售统计（按类别）
    category_sales = db.session.query(
        Category.name,
        func.coalesce(func.sum(PurchaseLog.total_price), 0).label('total')
    ).outerjoin(Product, Product.category_id == Category.id).outerjoin(
        PurchaseLog, PurchaseLog.product_id == Product.id
    ).group_by(Category.id).order_by(desc('total')).all()

    return render_template('admin/dashboard.html',
                           user_count=user_count,
                           product_count=product_count,
                           order_count=order_count,
                           total_revenue=total_revenue,
                           sales_ranking=sales_ranking,
                           category_sales=category_sales)


@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    """用户管理"""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/user/add', methods=['POST'])
@login_required
@role_required('admin')
def admin_user_add():
    """添加销售人员"""
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'sales')

    if User.query.filter_by(username=username).first():
        flash('用户名已存在。', 'danger')
        return redirect(url_for('admin_users'))

    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)

    log_operation(f'添加用户: {username} ({role})')
    db.session.commit()

    flash(f'用户 "{username}" 添加成功。', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/user/reset-password/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_user_reset_password(user_id):
    """重置用户密码"""
    user = db.session.get(User, user_id)
    if user:
        new_password = request.form.get('new_password', '123456')
        user.set_password(new_password)
        log_operation(f'重置用户 {user.username} 的密码')
        db.session.commit()
        flash(f'用户 "{user.username}" 的密码已重置。', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/user/toggle/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_user_toggle(user_id):
    """启用/禁用用户"""
    user = db.session.get(User, user_id)
    if user:
        user.is_active = not user.is_active
        status = '启用' if user.is_active else '禁用'
        log_operation(f'{status}用户: {user.username}')
        db.session.commit()
        flash(f'用户 "{user.username}" 已{status}。', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def admin_user_delete(user_id):
    """删除用户"""
    user = db.session.get(User, user_id)
    if user and user.role != 'admin':
        name = user.username
        db.session.delete(user)
        log_operation(f'删除用户: {name}')
        db.session.commit()
        flash(f'用户 "{name}" 已删除。', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/operation-logs')
@login_required
@role_required('admin')
def admin_operation_logs():
    """操作日志查看"""
    page = request.args.get('page', 1, type=int)
    logs = OperationLog.query.order_by(OperationLog.created_at.desc()).paginate(
        page=page, per_page=30, error_out=False)
    return render_template('admin/operation_logs.html', logs=logs)


# ═══════════════════════════════════════════════════════
#  数据分析 API & 可视化
# ═══════════════════════════════════════════════════════

@app.route('/analytics')
@login_required
@role_required('sales', 'admin')
def analytics():
    """数据分析大屏"""
    return render_template('analytics.html')


@app.route('/api/analytics/sales-trend')
@login_required
@role_required('sales', 'admin')
def api_sales_trend():
    """销售趋势 API — 支持日/周/月"""
    period = request.args.get('period', 'daily')

    if period == 'weekly':
        # 最近4周
        now = datetime.utcnow()
        data = []
        for i in range(3, -1, -1):
            start = now - timedelta(days=now.weekday() + 7 * (i + 1))
            end = start + timedelta(days=7)
            total = db.session.query(func.sum(Order.total_amount)).filter(
                Order.created_at >= start, Order.created_at < end,
                Order.status != 'cancelled'
            ).scalar() or 0
            data.append({'label': f'第{i+1}周', 'value': round(total, 2)})
        return jsonify(data)

    elif period == 'monthly':
        # 最近6个月
        now = datetime.utcnow()
        data = []
        for i in range(5, -1, -1):
            year = now.year
            month = now.month - i
            if month <= 0:
                month += 12
                year -= 1
            total = db.session.query(func.sum(Order.total_amount)).filter(
                func.extract('year', Order.created_at) == year,
                func.extract('month', Order.created_at) == month,
                Order.status != 'cancelled'
            ).scalar() or 0
            data.append({'label': f'{month}月', 'value': round(total, 2)})
        return jsonify(data)

    else:
        # 最近7天
        data = _get_sales_trend(7)
        return jsonify(data)


def _get_sales_trend(days=7):
    """获取最近N天的销售趋势"""
    data = []
    for i in range(days - 1, -1, -1):
        date = datetime.utcnow().date() - timedelta(days=i)
        day_start = datetime.combine(date, datetime.min.time())
        day_end = datetime.combine(date, datetime.max.time())
        total = db.session.query(func.sum(Order.total_amount)).filter(
            Order.created_at >= day_start, Order.created_at < day_end,
            Order.status != 'cancelled'
        ).scalar() or 0
        count = Order.query.filter(
            Order.created_at >= day_start, Order.created_at < day_end,
            Order.status != 'cancelled'
        ).count()
        data.append({
            'label': date.strftime('%m/%d'),
            'value': round(total, 2),
            'orders': count
        })
    return data


@app.route('/api/analytics/category-distribution')
@login_required
@role_required('sales', 'admin')
def api_category_distribution():
    """商品类别销售分布"""
    data = db.session.query(
        Category.name,
        func.coalesce(func.sum(PurchaseLog.total_price), 0).label('total')
    ).outerjoin(Product, Product.category_id == Category.id).outerjoin(
        PurchaseLog, PurchaseLog.product_id == Product.id
    ).group_by(Category.id).order_by(desc('total')).all()
    return jsonify([{'name': name, 'value': round(total, 2)} for name, total in data])


@app.route('/api/analytics/top-products')
@login_required
@role_required('sales', 'admin')
def api_top_products():
    """商品销售排行榜"""
    products = Product.query.filter_by(is_active=True).order_by(
        Product.sales_count.desc()
    ).limit(15).all()
    return jsonify([{
        'name': p.name,
        'sales': p.sales_count,
        'stock': p.stock,
        'price': p.price
    } for p in products])


@app.route('/api/analytics/user-regions')
@login_required
@role_required('admin')
def api_user_regions():
    """用户地域分布"""
    regions = db.session.query(
        User.region,
        func.count(User.id).label('cnt'),
        func.sum(User.total_spent).label('spent')
    ).filter(User.region != '').group_by(User.region).all()
    return jsonify([{
        'region': r,
        'count': c,
        'total_spent': round(s or 0, 2)
    } for r, c, s in regions])


@app.route('/api/analytics/anomaly-detection')
@login_required
@role_required('sales', 'admin')
def api_anomaly_detection():
    """销售异常检测 — 基于最近订单量与历史均值的偏差"""
    now = datetime.utcnow()

    # 最近7天每天的订单量
    recent = []
    for i in range(6, -1, -1):
        date = now.date() - timedelta(days=i)
        cnt = Order.query.filter(
            func.date(Order.created_at) == date
        ).count()
        recent.append({'date': str(date), 'count': cnt})

    # 计算均值与标准差
    counts = [r['count'] for r in recent]
    if counts:
        mean = sum(counts) / len(counts)
        std = (sum((c - mean) ** 2 for c in counts) / len(counts)) ** 0.5

        anomalies = []
        for r in recent:
            if std > 0 and abs(r['count'] - mean) > 2 * std:
                anomalies.append({
                    'date': r['date'],
                    'count': r['count'],
                    'expected': round(mean, 1),
                    'type': 'spike' if r['count'] > mean else 'drop'
                })
    else:
        anomalies = []

    return jsonify({'recent': recent, 'anomalies': anomalies})


# ═══════════════════════════════════════════════════════
#  用户画像 API
# ═══════════════════════════════════════════════════════

@app.route('/api/analytics/user-profile')
@login_required
def api_user_profile():
    """返回当前用户的画像数据"""
    user = current_user
    purchase_count = PurchaseLog.query.filter_by(user_id=user.id).count()
    categories = db.session.query(
        Category.name,
        func.count(PurchaseLog.id).label('cnt')
    ).join(Product, Product.category_id == Category.id).join(
        PurchaseLog, PurchaseLog.product_id == Product.id
    ).filter(PurchaseLog.user_id == user.id).group_by(
        Category.id
    ).order_by(desc('cnt')).all()

    return jsonify({
        'username': user.username,
        'region': user.region,
        'total_spent': round(user.total_spent, 2),
        'purchase_count': purchase_count,
        'preferred_category': user.preferred_category,
        'category_breakdown': [{'name': n, 'count': c} for n, c in categories]
    })


# ═══════════════════════════════════════════════════════
#  推荐系统 API
# ═══════════════════════════════════════════════════════

@app.route('/api/recommendations')
@login_required
def api_recommendations():
    """个性化推荐 — 基于用户偏好 + 协同过滤"""
    # 1. 基于偏好的推荐
    preference_recs = []
    if current_user.preferred_category:
        cat = Category.query.filter_by(name=current_user.preferred_category).first()
        if cat:
            preference_recs = Product.query.filter_by(
                category_id=cat.id, is_active=True
            ).order_by(Product.sales_count.desc()).limit(6).all()

    # 2. 协同过滤：基于购买历史的推荐
    cf_recs = _get_collaborative_filtering_recs(current_user.id)

    # 去重合并
    seen = set(p.id for p in preference_recs)
    all_recs = [{
        'id': p.id, 'name': p.name, 'price': p.price,
        'image_url': p.image_url, 'category': p.category.name if p.category else '',
        'sales_count': p.sales_count,
        'source': 'preference'
    } for p in preference_recs]

    for p in cf_recs:
        if p.id not in seen:
            all_recs.append({
                'id': p.id, 'name': p.name, 'price': p.price,
                'image_url': p.image_url, 'category': p.category.name if p.category else '',
                'sales_count': p.sales_count,
                'source': 'collaborative'
            })
            seen.add(p.id)

    return jsonify(all_recs)


def _get_collaborative_filtering_recs(user_id, limit=6):
    """协同过滤推荐"""
    # 找到该用户购买过的商品
    user_purchases = db.session.query(PurchaseLog.product_id).filter_by(
        user_id=user_id
    ).distinct().all()
    user_product_ids = [p[0] for p in user_purchases]

    if not user_product_ids:
        # 无购买记录，推荐热销商品
        return Product.query.filter_by(is_active=True).order_by(
            Product.sales_count.desc()).limit(limit).all()

    # 找到也购买了这些商品的其他用户
    similar_users = db.session.query(PurchaseLog.user_id).filter(
        PurchaseLog.product_id.in_(user_product_ids),
        PurchaseLog.user_id != user_id
    ).distinct().subquery()

    # 这些相似用户还买了什么（排除当前用户已购买的）
    recs = db.session.query(
        PurchaseLog.product_id,
        func.count(PurchaseLog.id).label('cnt')
    ).filter(
        PurchaseLog.user_id.in_(similar_users),
        ~PurchaseLog.product_id.in_(user_product_ids)
    ).group_by(PurchaseLog.product_id).order_by(
        desc('cnt')
    ).limit(limit).all()

    result = []
    for pid, cnt in recs:
        p = db.session.get(Product, pid)
        if p and p.is_active:
            result.append(p)
    return result


# ═══════════════════════════════════════════════════════
#  数据导出 API
# ═══════════════════════════════════════════════════════

@app.route('/api/export/sales')
@login_required
@role_required('sales', 'admin')
def api_export_sales():
    """导出销售数据 CSV"""
    import csv
    from io import StringIO

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['订单ID', '用户', '金额', '状态', '时间'])
    orders = Order.query.order_by(Order.created_at.desc()).limit(1000).all()
    for o in orders:
        writer.writerow([o.id, o.user.username if o.user else '', o.total_amount, o.status, o.created_at])

    output = si.getvalue()
    si.close()
    return output, 200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename=sales_export.csv'
    }


# ═══════════════════════════════════════════════════════
#  初始化数据库
# ═══════════════════════════════════════════════════════

@app.cli.command('init-db')
def init_db():
    """初始化数据库和示例数据"""
    db.create_all()

    # 创建默认类别
    categories = ['电子产品', '服装鞋帽', '图书教育', '家居生活', '食品饮料', '运动户外']
    for name in categories:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name))

    # 创建管理员
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@smartpick.com', role='admin', region='广州')
        admin.set_password('admin123')
        db.session.add(admin)

    # 创建销售人员
    if not User.query.filter_by(username='merchant1').first():
        sales = User(username='merchant1', email='merchant1@smartpick.com', role='sales', region='深圳')
        sales.set_password('merchant123')
        db.session.add(sales)

    # 创建测试用户
    if not User.query.filter_by(username='user1').first():
        user = User(username='user1', email='user1@example.com', role='customer', region='北京')
        user.set_password('user123')
        db.session.add(user)

    db.session.commit()

    # 创建示例商品
    if Product.query.count() == 0:
        cats = {c.name: c.id for c in Category.query.all()}
        sample_products = [
            ('iPhone 15 Pro Max', '苹果最新旗舰手机，搭载A17芯片', 8999, 50, '电子产品'),
            ('MacBook Air M3', '轻薄笔记本电脑，M3芯片', 7999, 30, '电子产品'),
            ('AirPods Pro 2', '主动降噪耳机', 1899, 100, '电子产品'),
            ('iPad Air', '10.9英寸平板电脑', 4399, 40, '电子产品'),
            ('机械键盘 K8 Pro', '87键RGB机械键盘', 599, 80, '电子产品'),
            ('运动跑鞋 Ultra', '轻便透气跑步鞋', 699, 60, '服装鞋帽'),
            ('纯棉T恤', '舒适透气纯棉面料', 99, 200, '服装鞋帽'),
            ('冬季羽绒服', '90%白鸭绒填充', 899, 45, '服装鞋帽'),
            ('Python编程入门', '零基础学Python', 59, 150, '图书教育'),
            ('数据结构与算法', '经典算法教材', 79, 120, '图书教育'),
            ('机器学习实战', 'AI入门实战教程', 89, 100, '图书教育'),
            ('北欧风台灯', '简约设计LED台灯', 199, 70, '家居生活'),
            ('记忆棉枕头', '慢回弹护颈枕', 159, 90, '家居生活'),
            ('保温杯 500ml', '304不锈钢保温杯', 89, 150, '家居生活'),
            ('坚果礼盒', '每日坚果混合装', 129, 80, '食品饮料'),
            ('有机绿茶', '高山有机绿茶250g', 69, 120, '食品饮料'),
            ('瑜伽垫', '加厚防滑瑜伽垫', 129, 55, '运动户外'),
            ('登山背包 40L', '户外防水登山包', 299, 35, '运动户外'),
            ('篮球 标准7号', '室内外通用篮球', 159, 50, '运动户外'),
            ('智能手表 S3', '全天候心率监测', 1299, 25, '电子产品'),
        ]
        for name, desc, price, stock, cat_name in sample_products:
            p = Product(
                name=name, description=desc, price=price,
                stock=stock, category_id=cats.get(cat_name),
                sales_count=0
            )
            db.session.add(p)
        db.session.commit()

    print('✅ 数据库初始化完成！')
    print('   管理员: admin / admin123')
    print('   销售人员: merchant1 / merchant123')
    print('   测试用户: user1 / user123')


# ── 启动入口 ───────────────────────────────────────────
if __name__ == '__main__':
    with app.app_context():
        db_path = os.path.join(app.config['BASE_DIR'] if 'BASE_DIR' in dir() else os.path.dirname(__file__),
                               'data', 'ecommerce.db')
        if not os.path.exists(db_path):
            db.create_all()
            print('数据库已创建，请运行: flask init-db')
    app.run(debug=True, host='0.0.0.0', port=5000)
