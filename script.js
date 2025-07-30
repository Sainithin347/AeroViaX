// Optional: Scroll to top on page load
const bookBtn = document.getElementById("bookNowBtn");
const navBookBtn = document.getElementById("nav-book-btn");

window.addEventListener("scroll", () => {
    const triggerPoint = bookBtn.getBoundingClientRect().bottom;
    
    if (triggerPoint < 0) {
        navBookBtn.style.display = "inline-block";
    } else {
        navBookBtn.style.display = "none";
    }
});
window.onload = function () {
  window.scrollTo(0, 0);
};
const taglines = [
    "Smart Skies. Smarter Solutions.",
    "Aerial Services for Multiple Industries.",
    "Empowering Fields, Frames & Frontiers.",
    "Agriculture,Photography,and Mapping."
  ];

  const textEl = document.getElementById("dynamic-text");
  let index = 0;

  function updateText() {
    textEl.classList.remove("fade-in");
    textEl.classList.add("fade-out");

    setTimeout(() => {
      textEl.textContent = taglines[index];
      textEl.classList.remove("fade-out");
      textEl.classList.add("fade-in");
      index = (index + 1) % taglines.length;
    }, 500); // fade out duration
  }

  // First load
  setInterval(updateText, 4000);
    function updateWhatsAppLink() {
    const service = document.getElementById('service').value;
    const name = document.getElementById('firstname').value;
    const text = `Hi, I want to book a drone for ${service ? service : '...'} from AeroViaX.${name ? '%0AName: ' + name : ''}`;
    whatsappBtn.href = `https://wa.me/916281805363?text=${encodeURIComponent(text)}`;
  }