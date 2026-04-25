from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SubmitField, PasswordField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, URL, Email, Optional
from flask_ckeditor import CKEditorField


class CreatePostForm(FlaskForm):
    title      = StringField("Blog Post Title", validators=[DataRequired()])
    subtitle   = StringField("Subtitle",        validators=[DataRequired()])
    # NEW: optional direct image upload; falls back to URL if blank
    img_file   = FileField("Upload Image", validators=[
                     FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'],
                                 'Images only!')])
    img_url    = StringField("OR paste Image URL", validators=[Optional(), URL()])
    # NEW: comma-separated tags e.g. "python, flask, web"
    tags       = StringField("Tags (comma-separated)", validators=[Optional()])
    # NEW: draft/publish toggle
    is_published = BooleanField("Publish now?", default=True)
    body       = CKEditorField("Blog Content", validators=[DataRequired()])
    submit     = SubmitField("Submit Post")


class RegisterForm(FlaskForm):
    name     = StringField(  label="Name",     validators=[DataRequired()])
    email    = StringField(  label="Email",    validators=[DataRequired(), Email()])
    password = PasswordField(label="Password", validators=[DataRequired()])
    submit   = SubmitField("Sign Me Up")


class LoginForm(FlaskForm):
    email    = StringField(  label="Email",    validators=[DataRequired(), Email()])
    password = PasswordField(label="Password", validators=[DataRequired()])
    submit   = SubmitField("Let Me In")


class CommentForm(FlaskForm):
    comment_text = CKEditorField("Comment", validators=[DataRequired()])
    submit       = SubmitField("SUBMIT COMMENT")


class UserProfileForm(FlaskForm):
    """NEW: lets users edit their bio on their profile page."""
    bio    = TextAreaField("About Me", validators=[Optional()],
                           render_kw={"rows": 5,
                                      "placeholder": "Tell readers a bit about yourself…"})
    submit = SubmitField("Save Profile")


class ResetRequestForm(FlaskForm):
    """Step 1 of password reset — enter your email."""
    email  = StringField(label="Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Send Reset Link")


class ResetPasswordForm(FlaskForm):
    """Step 2 of password reset — enter new password."""
    password = PasswordField(label="New Password", validators=[DataRequired()])
    confirm  = PasswordField(label="Confirm Password", validators=[DataRequired()])
    submit   = SubmitField("Reset Password")

    def validate_confirm(self, field):
        from wtforms import ValidationError
        if field.data != self.password.data:
            raise ValidationError("Passwords must match.")
