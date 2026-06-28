"""冷启动数据生成 — 模拟用户消费记录、浏览日志、登录日志"""
import random
import sys
from datetime import datetime, timedelta
from collections import defaultdict

from app import app
from models import db, User, Product, Category
from models import PurchaseLog, BrowseLog, LoginLog, OperationLog

# ── 配置 ────────────────────────────────────────────────
random.seed(20260628)

REGIONS = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '南京', '西安', '重庆']
USER_POOL = [
    # (username, email, region, tier)
    # tier: heavy=高频高价, medium=中频中价, light=低频低价, browser=只看不买
    ('buyer_zhang', 'zhang@qq.com', '北京', 'heavy'),
    ('buyer_li', 'li@qq.com', '上海', 'heavy'),
    ('buyer_wang', 'wang@163.com', '广州', 'heavy'),
    ('buyer_chen', 'chen@gmail.com', '深圳', 'heavy'),
    ('buyer_liu', 'liu@qq.com', '杭州', 'heavy'),

    ('shopper_zhao', 'zhao@163.com', '成都', 'medium'),
    ('shopper_huang', 'huang@qq.com', '武汉', 'medium'),
    ('shopper_wu', 'wu@gmail.com', '南京', 'medium'),
    ('shopper_zhou', 'zhou@qq.com', '西安', 'medium'),
    ('shopper_xu', 'xu@163.com', '重庆', 'medium'),
    ('shopper_sun', 'sun@qq.com', '北京', 'medium'),
    ('shopper_ma', 'ma@163.com', '上海', 'medium'),
    ('shopper_guo', 'guo@qq.com', '广州', 'medium'),
    ('shopper_he', 'he@gmail.com', '深圳', 'medium'),
    ('shopper_gao', 'gao@qq.com', '杭州', 'medium'),

    ('user_lin', 'lin@163.com', '成都', 'light'),
    ('user_yang', 'yang@qq.com', '武汉', 'light'),
    ('user_zheng', 'zheng@gmail.com', '南京', 'light'),
    ('user_hu', 'hu@qq.com', '西安', 'light'),
    ('user_tang', 'tang@163.com', '重庆', 'light'),
    ('user_deng', 'deng@qq.com', '北京', 'light'),
    ('user_xie', 'xie@163.com', '上海', 'light'),
    ('user_feng', 'feng@qq.com', '广州', 'light'),
    ('user_peng', 'peng@gmail.com', '深圳', 'light'),
    ('user_zhu', 'zhu@qq.com', '杭州', 'light'),

    ('visitor_a', 'va@test.com', '成都', 'browser'),
    ('visitor_b', 'vb@test.com', '武汉', 'browser'),
    ('visitor_c', 'vc@test.com', '北京', 'browser'),
    ('visitor_d', 'vd@test.com', '上海', 'browser'),
    ('visitor_e', 've@test.com', '广州', 'browser'),
]

# 各类别购买概率权重（电子产品最热门）
CATEGORY_WEIGHTS = {
    '电子产品': 0.30,
    '服装鞋帽': 0.18,
    '图书教育': 0.15,
    '家居生活': 0.15,
    '食品饮料': 0.12,
    '运动户外': 0.10,
}

# 各 tier 每周购买次数范围
TIER_PURCHASE_RANGE = {
    'heavy':  (4, 8),   # 每周 4-8 单
    'medium': (1, 3),
    'light':  (0, 1),
    'browser': (0, 0),
}

# 各 tier 每周浏览次数范围
TIER_BROWSE_RANGE = {
    'heavy':  (8, 20),
    'medium': (5, 12),
    'light':  (3, 8),
    'browser': (10, 30),
}


def create_users():
    """创建模拟用户"""
    users = {}
    for username, email, region, tier in USER_POOL:
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(username=username, email=email, region=region, role='customer')
            u.set_password('123456')
            db.session.add(u)
            db.session.flush()
        u._tier = tier  # 临时属性
        users[username] = u
    db.session.commit()
    print(f'  Users: {len(users)} created/loaded')
    return users


def get_category_products():
    """获取类别→商品列表映射"""
    cats = {c.name: [p for p in c.products if p.is_active] for c in Category.query.all()}
    for name, prods in cats.items():
        print(f'  Products in [{name}]: {len(prods)}')
    return cats


def generate_data(users, cat_products):
    """为核心生成购买、浏览、登录数据"""
    now = datetime.utcnow()
    products = [p for prods in cat_products.values() for p in prods]
    all_purchases = []
    all_browses = []
    all_logins = []
    login_dates = defaultdict(set)

    # 过去 30 天，按天迭代
    for day_offset in range(30, 0, -1):
        date = now.date() - timedelta(days=day_offset)
        is_weekend = date.weekday() >= 5  # 周末更活跃
        day_mult = 1.5 if is_weekend else 1.0

        for username, user in users.items():
            tier = getattr(user, '_tier', 'light')

            # ── 登录 ──
            if random.random() < (0.6 * day_mult if tier != 'browser' else 0.3):
                # 一天内可能登录 1-3 次
                logins_today = random.choices([1, 2, 3], weights=[0.7, 0.25, 0.05])[0]
                for _ in range(logins_today):
                    hour = random.randint(7, 23)
                    login_time = datetime.combine(date, datetime.min.time()) + timedelta(
                        hours=hour, minutes=random.randint(0, 59))
                    if date not in login_dates.get(username, set()):
                        all_logins.append(LoginLog(
                            user_id=user.id,
                            ip_address=f'10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}',
                            login_time=login_time
                        ))
                        login_dates.setdefault(username, set()).add(date)

            # ── 浏览 ──
            browse_min, browse_max = TIER_BROWSE_RANGE[tier]
            browse_count = int(random.randint(browse_min, browse_max) * day_mult / 7)
            browsed_today = set()
            for _ in range(max(0, browse_count)):
                cat = random.choices(
                    list(CATEGORY_WEIGHTS.keys()),
                    weights=list(CATEGORY_WEIGHTS.values())
                )[0]
                prods = cat_products.get(cat, [])
                if not prods:
                    continue
                product = random.choice(prods)
                if product.id in browsed_today:
                    continue
                browsed_today.add(product.id)
                hour = random.randint(7, 23)
                browse_time = datetime.combine(date, datetime.min.time()) + timedelta(
                    hours=hour, minutes=random.randint(0, 59))
                all_browses.append(BrowseLog(
                    user_id=user.id,
                    product_id=product.id,
                    category_id=product.category_id,
                    ip_address=f'10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}',
                    duration_seconds=random.randint(10, 300),
                    created_at=browse_time
                ))

            # ── 购买 ──
            buy_min, buy_max = TIER_PURCHASE_RANGE[tier]
            buy_count_per_week = random.randint(buy_min, max(buy_min, buy_max))
            # 按天概率判断是否购买
            if random.random() < (buy_count_per_week / 7) * day_mult:
                # 一次购买 1-3 个商品
                items_in_order = random.choices([1, 2, 3], weights=[0.55, 0.35, 0.10])[0]
                order_purchases = set()
                for _ in range(items_in_order):
                    if len(order_purchases) >= 3:
                        break
                    cat = random.choices(
                        list(CATEGORY_WEIGHTS.keys()),
                        weights=list(CATEGORY_WEIGHTS.values())
                    )[0]
                    prods = cat_products.get(cat, [])
                    if not prods:
                        continue
                    product = random.choice(prods)
                    if product.id in order_purchases:
                        continue
                    order_purchases.add(product.id)

                    quantity = random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
                    quantity = min(quantity, product.stock) if product.stock > 0 else 1

                    hour = random.randint(9, 22)
                    purchase_time = datetime.combine(date, datetime.min.time()) + timedelta(
                        hours=hour, minutes=random.randint(0, 59))

                    all_purchases.append(PurchaseLog(
                        user_id=user.id,
                        product_id=product.id,
                        category_id=product.category_id,
                        quantity=quantity,
                        unit_price=product.price,
                        total_price=product.price * quantity,
                        created_at=purchase_time
                    ))

                    # 更新商品销量
                    product.sales_count += quantity

                    # 更新用户消费
                    user.total_spent += product.price * quantity

    # ── 批量写入 ──
    print(f'\n  Generating {len(all_logins)} login logs...')
    db.session.bulk_save_objects(all_logins)

    print(f'  Generating {len(all_browses)} browse logs...')
    db.session.bulk_save_objects(all_browses)

    print(f'  Generating {len(all_purchases)} purchase records...')
    db.session.bulk_save_objects(all_purchases)

    db.session.commit()
    return len(all_purchases), len(all_browses), len(all_logins)


def update_user_preferences(users):
    """更新用户偏好类别和画像"""
    updated = 0
    for username, user in users.items():
        # 找到购买最多的类别
        result = db.session.query(
            PurchaseLog.category_id,
            db.func.sum(PurchaseLog.total_price).label('total')
        ).filter_by(user_id=user.id).group_by(
            PurchaseLog.category_id
        ).order_by(db.desc('total')).first()

        if result:
            cat = db.session.get(Category, result[0])
            if cat:
                user.preferred_category = cat.name
                updated += 1
    db.session.commit()
    print(f'  User preferences updated: {updated}')
    return updated


def main():
    with app.app_context():
        print('=== SmartPick Cold-Start Data Generator ===\n')

        print('[1/4] Creating users...')
        users = create_users()

        print('\n[2/4] Loading products...')
        cat_products = get_category_products()
        total_products = sum(len(v) for v in cat_products.values())
        if total_products == 0:
            print('ERROR: No products found! Run flask init-db first.')
            sys.exit(1)

        print(f'\n[3/4] Generating 30-day activity data...')
        n_purchases, n_browses, n_logins = generate_data(users, cat_products)

        print(f'\n[4/4] Updating user preferences...')
        n_prefs = update_user_preferences(users)

        # ── 统计 ──
        total_revenue = db.session.query(
            db.func.sum(PurchaseLog.total_price)
        ).scalar() or 0
        total_users = User.query.filter_by(role='customer').count()
        total_orders = PurchaseLog.query.count()

        print(f'\n{"="*50}')
        print(f'  Data generation complete!')
        print(f'  {"="*50}')
        print(f'  Simulated users:    {total_users}')
        print(f'  Login logs:         {n_logins}')
        print(f'  Browse logs:        {n_browses}')
        print(f'  Purchase records:   {n_purchases}')
        print(f'  Total revenue:      ${total_revenue:,.2f}')
        print(f'  Top product sales:  {Product.query.order_by(db.desc(Product.sales_count)).first().sales_count}')
        print(f'{"="*50}')


if __name__ == '__main__':
    main()
