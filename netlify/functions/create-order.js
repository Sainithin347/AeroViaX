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

  const keyId = process.env.RAZORPAY_KEY_ID;
  const keySecret = process.env.RAZORPAY_KEY_SECRET;

  if (!keyId || !keySecret) {
    return {
      statusCode: 500,
      headers: withCors(jsonHeaders),
      body: JSON.stringify({ error: "Razorpay keys are not configured on server" }),
    };
  }

  try {
    const payload = JSON.parse(event.body || "{}");
    const amount = Number(payload.amount || 0);
    const currency = payload.currency || "INR";
    const receipt = payload.receipt || `rcpt_${Date.now()}`;
    const notes = payload.notes || {};

    if (!amount || amount < 100) {
      return {
        statusCode: 400,
        headers: withCors(jsonHeaders),
        body: JSON.stringify({ error: "Invalid amount" }),
      };
    }

    const auth = Buffer.from(`${keyId}:${keySecret}`).toString("base64");
    const razorpayRes = await fetch("https://api.razorpay.com/v1/orders", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Basic ${auth}`,
      },
      body: JSON.stringify({
        amount,
        currency,
        receipt,
        notes,
      }),
    });

    const razorpayBody = await razorpayRes.json();

    if (!razorpayRes.ok) {
      return {
        statusCode: razorpayRes.status,
        headers: withCors(jsonHeaders),
        body: JSON.stringify({
          error: razorpayBody?.error?.description || "Failed to create Razorpay order",
        }),
      };
    }

    return {
      statusCode: 200,
      headers: withCors(jsonHeaders),
      body: JSON.stringify({
        id: razorpayBody.id,
        amount: razorpayBody.amount,
        currency: razorpayBody.currency,
        keyId,
      }),
    };
  } catch (error) {
    return {
      statusCode: 500,
      headers: withCors(jsonHeaders),
      body: JSON.stringify({ error: "Internal server error while creating order" }),
    };
  }
};
