from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
# Import your forms from the forms.py
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
import os
import smtplib
from dotenv import load_dotenv


load_dotenv()
app = Flask(__name__)
print(os.getenv("SECRET_KEY"))
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)

MAIL_ADDRESS = os.getenv("MAIL_ADDRESS")
MAIL_APP_PW = os.getenv("PASSWORD_KEY")
# TODO: Configure Flask-Login


# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DB_URI")
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES

# TODO: Create a User table for all your registered users.

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key =True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(100))

    # This will act like a List of BlogPost objects attached to each User.
    # The "author" refers to the author property in the BlogPost class.
    posts = relationship("BlogPost", back_populates="author")

    # *******Add parent relationship*******#
    # "comment_author" refers to the comment_author property in the Comment class.
    comments = relationship("Comment", back_populates="comment_author")


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Create Foreign Key, "users.id" the users refers to the tablename of User.
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    #Create reference to the User object. The "posts" refers to the posts property in the User class.
    author = relationship("User", back_populates="posts")

    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)

    # ***************Parent Relationship*************#
    comments = relationship("Comment", back_populates="parent_post", cascade="all, delete-orphan") # ONE TO MANY REL BETWEEN BlogPost object (Parent) & Comment object (Child).


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False) # text = blogpost body text

    # *******Add child relationship*******#
    # "users.id" The users refers to the tablename of the Users class.
    # "comments" refers to the comments property in the User class.
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    comment_author = relationship("User", back_populates="comments")

    # ***************Child Relationship*************#
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    parent_post = relationship("BlogPost", back_populates="comments")
    text: Mapped[str] = mapped_column(Text, nullable=False)



# For adding profile images to the comment section
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


with app.app_context():
    db.create_all()


login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)



def admin_only(function):          #takes route function
    @wraps(function)               # keep original function's name and info intact
    def decorated_function(*args, **kwargs):     # wrapper that run instead of your route first
        # 1. Safely check if they are logged in at all
        if not current_user.is_authenticated:
            return abort(401)
        # 2. IF ID IS NOT 1, THEN RETURN ABORT WITH 403 ERROR
        if current_user.id != 1:
            return abort(403)
        # OTHERWISE CONTINUE WITH THE ROUTE FUNCTION
        return function(*args, **kwargs)   # if user is admin, run the actual route
    return decorated_function   ## 3. Return the function reference WITHOUT parentheses!



# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit(): # DOES TWO THINGS AT ONCE: 1.CHECKS IF REQUEST.METHOD==POST, 2. VALIDATES FORM FIELDS

        # Check if user email is already present in the database
        result = db.session.execute(db.select(User).where(User.email == form.email.data))
        user = result.scalar()

        if user:    # IF USER EXISTS
            flash("You've already signed up with that email. Please login ")
            return redirect(url_for('login'))

        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256', salt_length=8) #HASH THE USER'S PASSWORD

        new_user = User(
            name = form.name.data,
            email = form.email.data,
            password = hashed_password
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('get_all_posts'))
    return render_template("register.html", form=form, current_user=current_user)


# TODO: Retrieve a user from the database based on their email. 
@app.route('/login', methods=["GET", "POST"])
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        email = login_form.email.data
        passwd = login_form.password.data

        #Find user by email
        result = (db.session.execute(db.select(User).where(User.email == email)) )
        user = result.scalar()

        #email not found
        if not user:
            flash("Email not found")
            return redirect(url_for('register'))

        elif not check_password_hash(user.password, passwd):
            flash("Incorrect Email or Password")
            return redirect(url_for('login'))

        else:
            login_user(user)
            return redirect(url_for('get_all_posts'))
    return render_template("login.html", login_form=login_form, current_user=current_user)



@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts, current_user=current_user)


# TODO: Allow logged-in users to comment on posts
# add the CommentForm to the route
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment on this post")
            return redirect(url_for('login'))

        new_comment = Comment(
            text = comment_form.comment_text.data,
            comment_author = current_user,
            parent_post = requested_post
        )
        db.session.add(new_comment)
        db.session.commit()
    return render_template("post.html", post=requested_post, current_user=current_user, comment_form=comment_form)




# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, current_user=current_user)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True, current_user=current_user)


# TODO: Use a decorator so only an admin user can delete a post
@admin_only
@app.route("/delete/<int:post_id>")
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)



@app.route("/contact", methods=["GET", "POST"])
def contact():
    # If the user clicks "Send" on the form
    if request.method == "POST":
        data = request.form
        send_email(data["name"], data["email"], data["phone"], data["message"])
        # Added current_user back in
        return render_template("contact.html", msg_sent=True, current_user=current_user)

    # If the user is just visiting the page normally (GET request)
    return render_template("contact.html", msg_sent=False, current_user=current_user)


def send_email(name, email, phone, message):
    email_message = f"Subject:New Message\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nMessage:{message}"

    with smtplib.SMTP_SSL("smtp.gmail.com", port=465) as connection:
        connection.login(MAIL_ADDRESS, MAIL_APP_PW)
        # Fixed the second argument to send the email to yourself
        connection.sendmail(
            from_addr=MAIL_ADDRESS,
            to_addrs=MAIL_ADDRESS,
            msg=email_message
        )



if __name__ == "__main__":
    app.run(debug=True, port=5001)
