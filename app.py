from flask import Flask, render_template, request, jsonify
import razorpay

app = Flask(__name__)

# Replace with your Razorpay LIVE key and secret
razorpay_client = razorpay.Client(auth=("rzp_test_7PoxAkSLJuNev9", "0JfMjDzw4iv45I2nWT8KCmDX"))

@app.route('/')
def index():
    return render_template("book.html")

@app.route('/create_order', methods=['POST'])
def create_order():
    amount = 149900  # ₹1499 in paise
    currency = 'INR'

    payment = razorpay_client.order.create(dict(amount=amount, currency=currency, payment_capture='1'))
    return jsonify({'order_id': payment['id']})

if __name__ == '__main__':
    app.run(debug=True)
