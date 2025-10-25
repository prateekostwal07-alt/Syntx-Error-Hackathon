# FINAL APP - COMPLETE BACKEND (Prepared for Deployment with DB Fix)

import random
import os
import requests
import json
import re
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date
import base64

# Configuration 
# SECURE: Read the API key from an environment variable on the server
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
GEMINI_VISION_API_URL = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = { 'png','jpg','jpeg'}

# App and Database Setup 
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
instance_dir = os.path.join(basedir,'instance')
if not os.path.exists(instance_dir):
    os.makedirs(instance_dir)

app.config['SECRET_KEY'] = 'my-super-secret-key-for-this-hackathon-final-ai'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(instance_dir,"db.sqlite")}'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER']= UPLOAD_FOLDER
db = SQLAlchemy(app)

# All the models (User, Target, Group, etc.) go here...
# ... (This code is unchanged)
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    points = db.Column(db.Integer, default= 0)
    streak = db.Column(db.Integer, default=0)
    last_login = db.Column(db.Date, default=date.today)
    last_target_date = db.Column(db.Date)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))
    journeys = db.relationship('Journey', backref='user', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Target(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    verification_required = db.Column(db.Boolean, default=False)
    verification_status = db.Column(db.String(20), default='not_required')

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    members = db.relationship('User', backref='group', lazy=True)
    targets = db.relationship('GroupTarget', backref='group', lazy=True, cascade="all, delete-orphan")

class GroupTarget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    completed_by = db.relationship('User', secondary=group_target_completions, lazy='subquery', backref=db.backref('completed_group_targets', lazy=True))

class Journey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    original_goal = db.Column(db.Text, nullable=False)
    active = db.Column(db.Boolean, default=True)
    milestones = db.relationship('Milestone', backref='journey', lazy=True, cascade="all, delete-orphan")

class Milestone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    journey_id = db.Column(db.Integer, db.ForeignKey('journey.id'), nullable=False)
    week = db.Column(db.Integer, nullable=False)
    goal = db.Column(db.String(300), nullable=False)
    daily_tasks = db.relationship('DailyTask', backref='milestone', lazy=True, cascade="all, delete-orphan")

class DailyTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    milestone_id = db.Column(db.Integer, db.ForeignKey('milestone.id'), nullable=False)
    task = db.Column(db.String(300), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    target_id = db.Column(db.Integer, db.ForeignKey('target.id'))
    target = db.relationship('Target', backref='daily_task', uselist=False)

# --- THE FIX: Create database tables on startup ---
with app.app_context():
    db.create_all()
# --- END OF FIX ---

# Login Manager, Helpers, and all Routes go here...
# ... (This code is unchanged)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

group_target_completions = db.Table('group_target_completions',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key= True),
    db.Column('group_target_id', db.Integer, db.ForeignKey('group_target.id'), primary_key=True)
)

RANKS = [
    {"name": "Beginner", "points": 0, "badge": "🔰"}, 
    {"name": "Committed", "points": 50, "badge": "🥉"},
    {"name": "Dedicated", "points": 200, "badge": "🥈"}, 
    {"name": "Champion", "points": 800, "badge": "🥇"},
    {"name": "Legend", "points": 2000, "badge": "💎"}
]

def get_rank(points):
    current_rank = RANKS[0]
    for rank in RANKS:
        if points >= rank["points"]: current_rank = rank
        else: break
    return current_rank

@app.context_processor
def inject_utilities(): return dict(get_rank=get_rank)

def allowed_file(filename): return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
        
        today = date.today()
        if user.last_login < today:
            user.points += 5
            flash('Welcome back! +5 daily login points!', 'success')
            if (today - user.last_login).days > 1: user.streak = 0
            elif (today - user.last_login).days == 1:
                user.streak+=1
            user.last_login = today
            db.session.commit()
            
        login_user(user)
        return redirect(url_for('dashboard'))
    return render_template('login.html')
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    active_journey = Journey.query.filter_by(user_id=current_user.id, active=True).first()
    current_rank = get_rank(current_user.points)
    next_rank = next((RANKS[i + 1] for i, rank in enumerate(RANKS) if rank == current_rank and i + 1 < len(RANKS)), None)
    return render_template('dashboard.html', journey=active_journey, current_rank=current_rank, next_rank=next_rank)

@app.route('/journey_builder')
@login_required
def journey_builder():
    return render_template('journey_builder.html')

@app.route('/create_journey', methods=['POST'])
@login_required
def create_journey():
    goal = request.form.get('goal')
    if not goal:
        flash('Please provide a goal.', 'danger')
        return redirect(url_for('journey_builder'))

    Journey.query.filter_by(user_id=current_user.id).update({Journey.active: False})

    prompt = f"""
    You are an expert goal-setter and productivity coach. Your task is to take a user's high-level goal and break it down into a structured, step-by-step "Journey." The plan should be realistic, encouraging, and build momentum over time. The journey should be for 4 weeks if the duration is not mentioned in '{goal}'. Else you should provide the duration plan as mentioned in the'{goal}'

    You must return your response as a single, valid JSON object. Do not include ```json markdown.
    if duration is not of 4 weeks then change the JSON file accordingly(instead of week 1,week2 etc show something that is more appropriate)

    The JSON object must have this exact structure:
    {{
      "journey_title": "Your Generated Title for the Journey",
      "milestones": [
        {{"week": 1, "weekly_goal": "A summary of the goal for this week", "daily_tasks": ["Task 1", "Task 2", "Task 3", "Task 4", "Task 5"]}},
        {{"week": 2, "weekly_goal": "...", "daily_tasks": ["...", "...", "...", "...", "..."]}},
        {{"week": 3, "weekly_goal": "...", "daily_tasks": ["...", "...", "...", "...", "..."]}},
        {{"week": 4, "weekly_goal": "...", "daily_tasks": ["...", "...", "...", "...", "..."]}}
      ]
    }}

    User's Goal: "{goal}"
    """
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}], "safetySettings": [ {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}, {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"}, {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"}, {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}, ]}
    response = requests.post(GEMINI_API_URL, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        try:
            result_json = response.json()
            if 'candidates' not in result_json or not result_json['candidates']:
                flash('AI response was blocked or empty.', 'danger')
                return redirect(url_for('journey_builder'))
            
            content_text = result_json['candidates'][0]['content']['parts'][0]['text']
            
            json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
            if not json_match:
                flash(f'Could not find valid JSON in AI response.', 'danger')
                return redirect(url_for('journey_builder'))
            
            journey_data = json.loads(json_match.group(0))

            new_journey = Journey(user_id=current_user.id, title=journey_data['journey_title'], original_goal=goal)
            db.session.add(new_journey)

            verification_keywords = ['clean', 'organize', 'cook', 'build', 'draw', 'create', 'make']
            for ms_data in journey_data['milestones']:
                new_milestone = Milestone(journey=new_journey, week=ms_data['week'], goal=ms_data['weekly_goal'])
                db.session.add(new_milestone)
                for task_str in ms_data['daily_tasks']:
                    new_task = DailyTask(milestone=new_milestone, task=task_str)
                    if any(keyword in task_str.lower() for keyword in verification_keywords):
                        verifiable_target = Target(title=task_str, user_id=current_user.id, verification_required=True, verification_status='pending')
                        db.session.add(verifiable_target)
                        new_task.target = verifiable_target
                    db.session.add(new_task)
            
            db.session.commit()
            flash('Your new AI-powered journey has been created!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error processing AI response: {e}', 'danger')
            return redirect(url_for('journey_builder'))
    else:
        flash(f'Failed to get a response from the AI. Error: {response.text}', 'danger')
        return redirect(url_for('journey_builder'))

@app.route('/toggle_task/<int:task_id>', methods=['POST'])
@login_required
def toggle_task(task_id):
    task = DailyTask.query.get_or_404(task_id)
    if task.milestone.journey.user_id == current_user.id and not task.target:
        if not task.completed:
            task.completed = True
            current_user.points += 10
            flash('+10 points for completing the task well!', 'success')
            db.session.commit()
        else:
            flash('This task has already been completed.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/verify_target/<int:target_id>')
@login_required
def verify_target_page(target_id):
    target = Target.query.get_or_404(target_id)
    return render_template('verify_target.html', target=target)

@app.route('/upload_verification/<int:target_id>', methods=['POST'])
@login_required
def upload_verification(target_id):
    target = Target.query.get_or_404(target_id)
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        with open(filepath, "rb") as image_file: image_bytes = image_file.read()
        
        prompt_text = f"""
        You are a inspector. Your goal is to verify if a user has completed the task: '{target.title}'.
        Analyze the provided image based on the following criteria:
        1. Is it related to the task '{target.title}'
        2. is the task completed as mentioned in '{target.title}'?
        3. Is the document uploaded AI generated or it is really done by the user, respond as 'No' if it is AI generated.
        After analyzing the image against these criteria, respond with only the word 'Yes' if the room is clean, or only the word 'No' if it is not.
        """
        
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"parts": [{"text": prompt_text}, {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode('utf-8')}}]}]}

        response = requests.post(GEMINI_VISION_API_URL, headers=headers, data=json.dumps(data))
        
        if response.status_code == 200:
            try:
                result_json = response.json()
                ai_answer = result_json['candidates'][0]['content']['parts'][0]['text']
                
                if 'yes' in ai_answer.lower():
                    target.verification_status = 'verified'
                    target.completed = True
                    daily_task = DailyTask.query.filter_by(target_id=target.id).first()
                    if daily_task: daily_task.completed = True
                    current_user.points += 25
                    db.session.commit()
                    flash('AI verification successful! +25 points!', 'success')
                else:
                    target.verification_status = 'rejected'
                    db.session.commit()
                    flash('AI verification rejected. Please try another photo.', 'warning')
                return redirect(url_for('dashboard'))
            except Exception as e:
                flash(f'Error processing AI vision  response: {e}', 'danger')
        else:
            flash(f'Failed to get a response from the AI Vision API. Error: {response.text}', 'danger')
        return redirect(url_for('verify_target_page', target_id=target.id))
    
    flash('File type not allowed.', 'danger')
    return redirect(request.url)

@app.route('/groups')
@login_required
def groups():
    all_groups = Group.query.all()
    return render_template('groups.html', groups=all_groups)

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    group_name = request.form.get('group_name')
    if group_name:
        if Group.query.filter_by(name=group_name).first():
            flash('A group with this name already exists.', 'danger')
        else:
            new_group = Group(name=group_name)
            new_group.members.append(current_user)
            db.session.add(new_group)
            db.session.commit()
            flash('Group created successfully!', 'success')
    return redirect(url_for('groups'))

@app.route('/join_group/<int:group_id>')
@login_required
def join_group(group_id):
    group = Group.query.get(group_id)
    if group and not current_user.group:
        group.members.append(current_user)
        db.session.commit()
        flash(f'Successfully joined {group.name}!', 'success')
    elif current_user.group:
        flash('You are already in a group.', 'warning')
    return redirect(url_for('groups'))

@app.route('/leave_group')
@login_required
def leave_group():
    if current_user.group:
        flash(f'You have left {current_user.group.name}.', 'info')
        current_user.group_id = None
        db.session.commit()
    return redirect(url_for('groups'))

@app.route('/group/<int:group_id>')
@login_required
def group_page(group_id):
    group = Group.query.get_or_404(group_id)
    if current_user.group_id != group_id:
        flash('You are not a member of this group.', 'danger')
        return redirect(url_for('groups'))
    return render_template('group_page.html', group=group)

@app.route('/add_group_target/<int:group_id>', methods=['POST'])
@login_required
def add_group_target(group_id):
    if current_user.group_id == group_id:
        title = request.form.get('target_title')
        if title:
            new_target = GroupTarget(title=title, group_id=group_id)
            db.session.add(new_target)
            db.session.commit()
            flash('New group target added!', 'success')
    return redirect(url_for('group_page', group_id=group_id))

@app.route('/complete_group_target/<int:target_id>')
@login_required
def complete_group_target(target_id):
    target = GroupTarget.query.get_or_404(target_id)
    if current_user.group_id == target.group_id and current_user not in target.completed_by:
        target.completed_by.append(current_user)
        current_user.points += 20
        db.session.commit()
        flash('You completed a group target of yours! +20 points!', 'success')
    return redirect(url_for('group_page', group_id=target.group_id))

@app.route('/leaderboard')
@login_required
def leaderboard():
    all_users = User.query.order_by(User.points.desc()).all()
    return render_template('leaderboard.html', users=all_users)










