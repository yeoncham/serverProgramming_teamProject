from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import requests
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MySQL 연결 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:root@localhost/restaurant'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 업로드 폴더
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.config['TEMPLATES_AUTO_RELOAD'] = True
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)

class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(250), nullable=False)
    address = db.Column(db.String(250))

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    restaurant_id = db.Column(db.Integer, db.ForeignKey('restaurant.id'))
    title = db.Column(db.String(200))
    content = db.Column(db.Text)
    rating = db.Column(db.Integer)
    image = db.Column(db.String(250))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    restaurant = db.relationship('Restaurant')
    user = db.relationship('User')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey('review.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text)
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)
    user = db.relationship('User')

class CommentLikeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(10))  # 'like' 또는 'dislike'


@app.route('/')
def index():
    sort = request.args.get('sort', 'latest')
    page = request.args.get('page', 1, type=int)
    per_page = 10

    if sort == 'popular':
        pagination = Review.query.order_by(Review.views.desc()).paginate(page=page, per_page=per_page)
    else:
        pagination = Review.query.order_by(Review.created_at.desc()).paginate(page=page, per_page=per_page)

    reviews = pagination.items
    return render_template('index.html', reviews=reviews, sort=sort, pagination=pagination)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash("회원가입 성공")
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if not user:
            flash("존재하지 않는 사용자입니다.")
            return render_template("login.html")

        if not check_password_hash(user.password, password):
            flash("비밀번호가 일치하지 않습니다.")
            return render_template("login.html")

        session['user_id'] = user.id
        flash("로그인 성공!")
        return redirect(url_for('index'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("로그아웃 되었습니다.")
    return redirect(url_for('index'))

@app.route('/review/create', methods=['GET', 'POST'])
def create_review():
    if request.method == 'POST':
        if 'user_id' not in session:
            flash("로그인이 필요합니다.")
            return redirect(url_for('login'))
        name = request.form['restaurant_name']
        title = request.form['title']
        content = request.form['content']
        rating = int(request.form['rating'])
        image = request.files.get('image')
        restaurant = Restaurant.query.filter_by(name=name).first()
        if not restaurant:
            restaurant = Restaurant(name=name)
            db.session.add(restaurant)
            db.session.commit()
        filename = None
        if image and image.filename != '':
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        review = Review(
            user_id=session['user_id'],
            restaurant_id=restaurant.id,
            restaurant=restaurant,
            title=title,
            content=content,
            rating=rating,
            image=filename
        )
        db.session.add(review)
        db.session.commit()
        flash("리뷰가 등록되었습니다.")
        return redirect(url_for('index'))
    return render_template('create_review.html')

@app.route('/review/<int:review_id>')
def view_review(review_id):
    review = Review.query.get_or_404(review_id)
    review.views += 1
    db.session.commit()
    comments = Comment.query.filter_by(review_id=review.id).all()
    return render_template('view_review.html', review=review, comments=comments)

@app.route('/review/edit/<int:review_id>', methods=['GET', 'POST'])
def edit_review(review_id):
    review = Review.query.get_or_404(review_id)
    if session.get('user_id') != review.user_id:
        flash('권한이 없습니다.')
        return redirect(url_for('index'))
    if request.method == 'POST':
        review.rating = request.form['rating']
        review.content = request.form['content']
        image = request.files.get('image')
        if image and image.filename != '':
            filename = secure_filename(image.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)
            review.image = filename
        if request.form.get('delete_image') == '1' and review.image:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], review.image))
            except FileNotFoundError:
                pass
            review.image = None
        db.session.commit()
        flash("리뷰가 수정되었습니다.")
        return redirect(url_for('view_review', review_id=review.id))
    return render_template('edit_review.html', review=review)

@app.route('/review/delete/<int:review_id>', methods=['POST'])
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)
    if review.user_id != session.get('user_id'):
        flash('삭제 권한이 없습니다.')
        return redirect(url_for('index'))
    comments = Comment.query.filter_by(review_id=review.id).all()
    for comment in comments:
        CommentLikeLog.query.filter_by(comment_id=comment.id).delete()
        db.session.delete(comment)
    db.session.delete(review)
    db.session.commit()
    flash('리뷰가 삭제되었습니다.')
    return redirect(url_for('index'))

@app.route('/restaurant/search', methods=['GET', 'POST'])
def restaurant_search():
    if request.method == 'POST':
        keyword = request.form['keyword']
        headers = {
            'X-Naver-Client-Id': '5qExCIwQD_V4DmKlpwYT',
            'X-Naver-Client-Secret': 'K_wWBcYDJd'
        }
        url = f"https://openapi.naver.com/v1/search/local.json?query={keyword}&display=5&start=1&sort=random"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            results = response.json()['items']
            return render_template('restaurant_search.html', results=results)
        else:
            flash('검색 실패')
    return render_template('restaurant_search.html')

@app.route('/restaurant/<int:restaurant_id>')
def restaurant_detail(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    reviews = Review.query.filter_by(restaurant_id=restaurant_id).order_by(Review.created_at.desc()).all()
    return render_template('restaurant_detail.html', restaurant=restaurant, reviews=reviews)

@app.route('/api/naver_search')
def naver_search():
    query = request.args.get('query')
    headers = {
        'X-Naver-Client-Id': '5qExCIwQD_V4DmKlpwYT',
        'X-Naver-Client-Secret': 'K_wWBcYDJd'
    }
    url = f"https://openapi.naver.com/v1/search/local.json?query={query}&display=5&start=1&sort=random"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return jsonify(response.json()['items'])
    else:
        return jsonify([])

@app.route('/search', methods=['GET'])
def search_reviews():
    keyword = request.args.get('q', '')
    reviews = []
    if keyword:
        reviews = Review.query.join(Restaurant).filter(
            (Restaurant.name.contains(keyword)) |
            (Review.title.contains(keyword))
        ).order_by(Review.created_at.desc()).all()
    return render_template('search_results.html', keyword=keyword, reviews=reviews)

@app.route('/comment/create/<int:review_id>', methods=['POST'])
def create_comment(review_id):
    content = request.form['content']
    user_id = session.get('user_id')
    if not user_id:
        flash("로그인이 필요합니다.")
        return redirect(url_for('login'))

    comment = Comment(review_id=review_id, user_id=user_id, content=content)
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('view_review', review_id=review_id))

@app.route('/comment/delete/<int:comment_id>', methods=['POST'])
def delete_comment(comment_id):
    user_id = session.get('user_id')
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != user_id:
        flash("삭제 권한이 없습니다.")
        return redirect(url_for('index'))
    CommentLikeLog.query.filter_by(comment_id=comment.id).delete()
    db.session.delete(comment)
    db.session.commit()
    flash("댓글이 삭제되었습니다.")
    return redirect(request.referrer or url_for('index'))

@app.route('/comment/edit/<int:comment_id>', methods=['POST'])
def edit_comment(comment_id):
    user_id = session.get('user_id')
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != user_id:
        flash("수정 권한이 없습니다.")
        return redirect(url_for('index'))
    new_content = request.form['new_content']
    comment.content = new_content
    db.session.commit()
    flash("댓글이 수정되었습니다.")
    return redirect(url_for('view_review', review_id=comment.review_id))

@app.route('/comment/like/<int:comment_id>')
def like_comment(comment_id):
    user_id = session.get('user_id')
    if not user_id:
        flash("로그인이 필요합니다.")
        return redirect(url_for('login'))
    existing_log = CommentLikeLog.query.filter_by(comment_id=comment_id, user_id=user_id).first()
    if existing_log:
        flash("이미 추천 또는 비추천을 하셨습니다.")
    else:
        comment = Comment.query.get_or_404(comment_id)
        comment.likes += 1
        db.session.add(CommentLikeLog(comment_id=comment_id, user_id=user_id, action='like'))
        db.session.commit()
        flash("추천 완료")
    return redirect(request.referrer or url_for('index'))

@app.route('/comment/dislike/<int:comment_id>')
def dislike_comment(comment_id):
    user_id = session.get('user_id')
    if not user_id:
        flash("로그인이 필요합니다.")
        return redirect(url_for('login'))
    existing_log = CommentLikeLog.query.filter_by(comment_id=comment_id, user_id=user_id).first()
    if existing_log:
        flash("이미 추천 또는 비추천을 하셨습니다.")
    else:
        comment = Comment.query.get_or_404(comment_id)
        comment.dislikes += 1
        db.session.add(CommentLikeLog(comment_id=comment_id, user_id=user_id, action='dislike'))
        db.session.commit()
        flash("비추천 완료")
    return redirect(request.referrer or url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
