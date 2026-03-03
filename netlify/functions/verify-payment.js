const crypto = require("crypto");

const jsonHeaders = {
  "Content-Type": "application/json",
};

function withCors(headers = {}) {
  return {
    ...headers,
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
  };
}

function safeEqual(a, b) {
  const aBuffer = Buffer.from(a || "", "utf8");
  const bBuffer = Buffer.from(b || "", "utf8");
  if (aBuffer.length !== bBuffer.length) {
    return false;
  }
  return crypto.timingSafeEqual(aBuffer, bBuffer);
}

exports.handler = async (event) => {
  if (event.httpMethod === "OPTIONS") {
    return {
      statusCode: 204,
      headers: withCors(),
      body: "",
    };
  }

  if (event.httpMethod !== "POST") {
    return {
      statusCode: 405,
      headers: withCors(jsonHeaders),
      body: JSON.stringify({ error: "Method not allowed" }),
    };
  }

  const keySecret = process.env.RAZORPAY_KEY_SECRET;
  if (!keySecret) {
    return {
      statusCode: 500,
      headers: withCors(jsonHeaders),
      body: JSON.stringify({ error: "Razorpay secret is not configured on server" }),
    };
  }

  try {
    const payload = JSON.parse(event.body || "{}");
    const orderId = payload.razorpay_order_id;
    const paymentId = payload.razorpay_payment_id;
    const signature = payload.razorpay_signature;

    if (!orderId || !paymentId || !signature) {
      return {
        statusCode: 400,
        headers: withCors(jsonHeaders),
        body: JSON.stringify({ verified: false, error: "Missing payment verification fields" }),
      };
    }

    const bodyToSign = `${orderId}|${paymentId}`;
    const expectedSignature = crypto
      .createHmac("sha256", keySecret)
      .update(bodyToSign)
      .digest("hex");

    const verified = safeEqual(expectedSignature, signature);

    return {
      statusCode: verified ? 200 : 400,
      headers: withCors(jsonHeaders),
      body: JSON.stringify({ verified }),
    };
  } catch (error) {
    return {
      statusCode: 500,
      headers: withCors(jsonHeaders),
      body: JSON.stringify({ verified: false, error: "Internal server error while verifying payment" }),
    };
  }
};
