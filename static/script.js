document.addEventListener("DOMContentLoaded", function () {
    const container = document.getElementById("providers-container");
    const modal = document.getElementById("providerModal");
    const modalBody = document.getElementById("modalBody");
    const serviceFilter = document.getElementById("serviceFilter");
    const searchInput = document.getElementById("searchInput") || document.getElementById("nameSearch");
    const searchBtn = document.getElementById("searchBtn");

    let allProviders = [];

    function populateServiceOptions(providers) {
        if (!serviceFilter) return;
        const previousValue = serviceFilter.value || "all";
        const services = [...new Set(providers.map((p) => p.service).filter(Boolean))].sort();

        serviceFilter.innerHTML = '<option value="all">All Services</option>';
        services.forEach((service) => {
            const option = document.createElement("option");
            option.value = service;
            option.textContent = service;
            serviceFilter.appendChild(option);
        });

        if (services.includes(previousValue) || previousValue === "all") {
            serviceFilter.value = previousValue;
        } else {
            serviceFilter.value = "all";
        }
    }

    function loadProviders() {
        fetch("/api/providers")
            .then((res) => res.json())
            .then((data) => {
                allProviders = data;
                populateServiceOptions(allProviders);
                displayProviders(allProviders);
            })
            .catch((err) => console.error(err));
    }

    function displayProviders(providers) {
        if (!container) return;
        container.innerHTML = "";

        if (providers.length === 0) {
            container.innerHTML = "<p style='color:white;'>No providers found</p>";
            return;
        }

        providers.forEach((provider) => {
            const card = document.createElement("div");
            card.className = "provider-card";
            const ratingValue = Number(provider.rating || 0).toFixed(1);

            card.innerHTML = `
                <div class="card-top">
                    <h3>${provider.company}</h3>
                    <div class="rating-badge"><span class="star-icon">&#9733;</span> ${ratingValue}</div>
                </div>
                <div class="service-badge">${provider.service}</div>
                <button class="price-box">Rs ${provider.price}</button>
            `;

            card.querySelector(".price-box").onclick = function () {
                openModal(provider);
            };

            container.appendChild(card);
        });
    }

    function applyFilters() {
        let filtered = allProviders;
        const selectedService = serviceFilter ? serviceFilter.value : "";
        const searchText = searchInput ? searchInput.value.toLowerCase() : "";

        if (selectedService && selectedService !== "all") {
            filtered = filtered.filter((p) => p.service === selectedService);
        }

        if (searchText) {
            filtered = filtered.filter((p) =>
                p.company.toLowerCase().includes(searchText)
            );
        }

        displayProviders(filtered);
    }

    function openModal(provider) {
        if (!modal || !modalBody) return;
        let createdOrderId = "";

        modalBody.innerHTML = `
            <div class="modal-card">
                <h2>${provider.company}</h2>

                <div class="info-row">
                    <span>Distributor</span>
                    <span>${provider.distributor}</span>
                </div>

                <div class="info-row">
                    <span>Service</span>
                    <span>${provider.service}</span>
                </div>

                <div class="info-row">
                    <span>Location</span>
                    <span>${provider.location}</span>
                </div>

                <div class="price-box">Rs ${provider.price}</div>

                <input type="text" id="custName" placeholder="Full Name">
                <input type="email" id="custEmail" placeholder="Email Address">
                <input type="text" id="custPhone" placeholder="Phone Number">

                <button class="otp-btn" id="sendOtpBtn">Send OTP</button>

                <div id="otpSection" style="display:none;">
                    <input type="text" id="otpInput" placeholder="Enter OTP">
                    <button class="verify-btn" id="verifyOtpBtn">
                        Verify and Pay Rs ${provider.price}
                    </button>
                </div>
            </div>
        `;

        modal.style.display = "flex";

        document.getElementById("sendOtpBtn").onclick = function () {
            const phone = document.getElementById("custPhone").value.trim();
            if (!phone) return alert("Enter phone number");

            fetch("/send-otp", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ phone })
            })
                .then((res) => res.json())
                .then((data) => {
                    if (data.status === "success") {
                        const otpValue = data.otp || data.code || "";
                        alert("OTP sent: " + otpValue);
                        document.getElementById("otpSection").style.display = "block";
                        if (otpValue) {
                            document.getElementById("otpInput").value = otpValue;
                        }
                    } else {
                        alert("OTP failed");
                    }
                });
        };

        document.getElementById("verifyOtpBtn").onclick = function () {
            const name = document.getElementById("custName").value.trim();
            const email = document.getElementById("custEmail").value.trim();
            const phone = document.getElementById("custPhone").value.trim();
            const otp = document.getElementById("otpInput").value.trim();

            if (!name || !email || !phone || !otp) {
                return alert("Fill all fields and OTP");
            }

            fetch("/verify-otp", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ phone, otp })
            })
                .then((res) => res.json())
                .then((data) => {
                    if (data.status !== "verified") return alert("Invalid OTP");

                    fetch("/create-order", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            distributor_id: provider.id,
                            name,
                            email,
                            phone,
                            amount: provider.price,
                            service: provider.service,
                            provider: provider.company
                        })
                    })
                        .then((res) => res.json().then((payload) => {
                            if (!res.ok) {
                                throw new Error(payload.error || "Server error");
                            }
                            return payload;
                        }))
                        .then((order) => {
                            createdOrderId = order.id || "";
                            const keyId =
                                (window.APP_CONFIG && window.APP_CONFIG.razorpayKeyId) || "";
                            if (!keyId) {
                                alert("Payment key is not configured on server");
                                return;
                            }

                            const options = {
                                key: keyId,
                                amount: order.amount,
                                currency: order.currency,
                                name: "AeroViaX",
                                description: provider.service + " Booking",
                                order_id: order.id,
                                handler: function (response) {
                                    fetch("/verify-payment", {
                                        method: "POST",
                                        headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify(response)
                                    })
                                        .then((res) => res.json())
                                        .then((result) => {
                                            if (result.status === "success") {
                                                window.location.href = result.redirect_url || "/p-success";
                                            } else {
                                                window.location.href = result.redirect_url || "/p-fail";
                                            }
                                        });
                                },
                                modal: {
                                    ondismiss: function () {
                                        window.location.href = "/p-fail?reason=Checkout%20window%20was%20closed%20before%20payment";
                                    }
                                }
                            };

                            new Razorpay(options).open();
                        })
                        .catch((err) => {
                            console.error(err);
                            alert("Payment initialization failed: " + err.message);
                        });
                });
        };
    }

    if (serviceFilter) {
        serviceFilter.addEventListener("change", applyFilters);
    }

    if (searchInput) {
        searchInput.addEventListener("input", applyFilters);
        searchInput.addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                applyFilters();
            }
        });
    }

    if (searchBtn) {
        searchBtn.addEventListener("click", applyFilters);
    }

    window.onclick = function (e) {
        if (e.target === modal) modal.style.display = "none";
    };

    loadProviders();
});
