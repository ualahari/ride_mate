from flask import Flask, render_template, request, redirect, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'smart_pool_viva_key'

db = SQLAlchemy(app)

# --- Database Models ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    gender = db.Column(db.String(20)) 
    emergency_contact = db.Column(db.String(20))

class Ride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    route_from = db.Column(db.String(100), nullable=False)
    route_to = db.Column(db.String(100), nullable=False)
    departure_time = db.Column(db.String(50), nullable=False)
    seats_available = db.Column(db.Integer, nullable=False)
    women_only = db.Column(db.Boolean, default=False) 
    helmet_status = db.Column(db.String(50), default="N/A")

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    passenger_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ride_id = db.Column(db.Integer, db.ForeignKey('ride.id'), nullable=False)
    rating = db.Column(db.Integer)

class SupportTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(100))
    message = db.Column(db.Text)

# --- Routes ---

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            session['user_id'] = user.id
            session['user_name'] = user.name
            return redirect('/dashboard')
        flash("Invalid email or password!")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form.get('password'))
        new_user = User(
            name=request.form.get('name'), email=request.form.get('email'), 
            password=hashed_pw, gender=request.form.get('gender'),
            emergency_contact=request.form.get('emergency_contact')
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            return redirect('/login')
        except:
            return "Email already exists!"
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect('/login')
    
    total_bookings = Booking.query.count()
    carbon_saved = total_bookings * 2.5
    ride_success = 92 + (total_bookings % 8)
    trust_score = round(4.5 + (min(total_bookings, 5) * 0.1), 1)
    eco_impact = "Platinum" if carbon_saved > 500 else "Gold" if carbon_saved > 100 else "Silver"
    
    is_women_only = request.args.get('women_only') == 'true'
    search_query = request.args.get('search', '')
    
    query = db.session.query(Ride, User).join(User, Ride.driver_id == User.id)
    if is_women_only: query = query.filter(Ride.women_only == True)
    if search_query: query = query.filter(Ride.route_to.contains(search_query))
    
    rides = query.all()
    return render_template('dashboard.html', user_name=session['user_name'], 
                           carbon_saved=carbon_saved, ride_success=ride_success, 
                           trust_score=trust_score, eco_impact=eco_impact, 
                           rides=rides, is_women_only=is_women_only)

@app.route('/offer_ride', methods=['GET', 'POST'])
def offer_ride():
    if 'user_id' not in session: return redirect('/login')
    if request.method == 'POST':
        new_ride = Ride(
            driver_id=session['user_id'], vehicle_type=request.form.get('vehicle_type'),
            route_from=request.form.get('route_from'), route_to=request.form.get('route_to'),
            departure_time=request.form.get('departure_time'), seats_available=request.form.get('seats_available'),
            women_only=True if request.form.get('women_only') == 'on' else False,
            helmet_status=request.form.get('helmet_status', 'N/A')
        )
        db.session.add(new_ride)
        db.session.commit()
        return redirect('/dashboard')
    return render_template('offer_ride.html')
@app.route('/book/<int:ride_id>', methods=['POST'])
def book_ride(ride_id):
    if 'user_id' not in session: 
        return redirect('/login')
        
    ride = Ride.query.get(ride_id)
    
    # 1. Check if the ride exists
    if not ride:
        flash("Error: Ride not found.", "error")
        return redirect('/dashboard')
        
    # 2. Check if the user is the driver
    if ride.driver_id == session['user_id']:
        # For testing, you can comment out the next two lines if you want to allow booking your own rides
        flash("You cannot book a ride you are driving! 🚫", "error")
        return redirect('/dashboard')
        
    # 3. Check if there are seats left
    if ride.seats_available <= 0:
        flash("Sorry, this ride is fully booked! 😔", "error")
        return redirect('/dashboard')
        
    # 4. If everything is good, make the booking!
    # Convert to int just to be safe, since form inputs sometimes save as strings
    ride.seats_available = int(ride.seats_available) - 1 
    
    db.session.add(Booking(passenger_id=session['user_id'], ride_id=ride.id))
    db.session.commit()
    
    flash("Seat booked successfully! 🎉", "success")
    return redirect(f'/live_tracking/{ride.id}')

@app.route('/live_tracking/<int:ride_id>')
def live_tracking(ride_id):
    if 'user_id' not in session: return redirect('/login')
    ride = Ride.query.get(ride_id)
    return render_template('live_tracking.html', ride=ride)

@app.route('/ride_history')
def ride_history():
    if 'user_id' not in session: return redirect('/login')
    
    # 1. Rides you offered (Driver view)
    offered = Ride.query.filter_by(driver_id=session['user_id']).all()
    
    # 2. Rides you booked (Passenger view) - Joining tables to get Driver Name
    booked = db.session.query(Ride, User, Booking.id).select_from(Booking)\
    .join(Ride, Booking.ride_id == Ride.id)\
    .join(User, Ride.driver_id == User.id)\
    .filter(Booking.passenger_id == session['user_id']).all()
    
    return render_template('ride_history.html', offered_rides=offered, booked_rides=booked)
@app.route('/support', methods=['GET', 'POST'])
def support():
    if 'user_id' not in session: return redirect('/login')
    if request.method == 'POST':
        # Logic to save a support ticket
        flash("Support request sent! We will contact you soon.")
        return redirect('/dashboard')
    return render_template('support.html')
@app.route('/manage_payments')
def manage_payments():
    # 1. Get user details (assuming you have a session)
    user_id = session.get('user_id')
    is_women_only = session.get('is_women_only', False)
    
    # 2. Fetch data from your database (Mock data shown here for example)
    # Replace this with an actual database query:
    # e.g., current_balance = db.execute("SELECT balance FROM users WHERE id = ?", user_id)
    current_balance = 1250.00 
    
    # Replace this with a query to your transactions table:
    # e.g., user_txns = db.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC", user_id)
    user_txns = [
        {"description": "Earned: Vellore to Chennai Airport", "date": "Oct 24, 2:30 PM", "amount": 800.00, "type": "credit"},
        {"description": "Paid: VIT to Katpadi Station", "date": "Oct 22, 9:15 AM", "amount": 50.00, "type": "debit"},
        {"description": "Wallet Top-up via UPI", "date": "Oct 20, 11:00 AM", "amount": 500.00, "type": "credit"}
    ]

    return render_template(
        'manage_payments.html', 
        wallet_balance=f"{current_balance:.2f}", 
        transactions=user_txns,
        is_women_only=is_women_only
    )
@app.route('/api/stats')
def get_stats():
    total = Booking.query.count()
    return jsonify({'carbon_saved': total * 2.5, 'ride_success': 92 + (total % 8), 'trust_score': round(4.5 + (min(total, 5) * 0.1), 1)})
@app.route('/end_ride/<int:ride_id>', methods=['GET', 'POST'])
def end_ride(ride_id):
    if 'user_id' not in session: 
        return redirect('/login')
        
    ride = Ride.query.get_or_404(ride_id)
    
    if request.method == 'POST':
        # Get the star rating from the form
        rating = request.form.get('rating')
        
        # Find the booking linked to this passenger and ride
        booking = Booking.query.filter_by(ride_id=ride.id, passenger_id=session['user_id']).first()
        
        if booking:
            # Save the rating to the database
            booking.rating = int(rating)
            db.session.commit()
            flash("Thank you! Your review has been submitted. 🌟", "success")
        else:
            # If the driver ends the ride
            flash("Ride completed successfully! 🏁", "success")
            
        return redirect('/dashboard')

    return render_template('review.html', ride=ride)
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)