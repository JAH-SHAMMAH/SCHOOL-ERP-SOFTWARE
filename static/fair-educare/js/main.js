// Smooth scrolling for navigation links
document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener("click", function (e) {
    e.preventDefault();
    const target = document.querySelector(this.getAttribute("href"));
    if (target) {
      target.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  });
});

// Header scroll effect
let lastScroll = 0;
window.addEventListener("scroll", () => {
  const header = document.querySelector("header");
  const currentScroll = window.pageYOffset;

  if (currentScroll > 100) {
    header.style.padding = "0.8rem 5%";
  } else {
    header.style.padding = "1.2rem 5%";
  }

  lastScroll = currentScroll;
});

// Intersection Observer for fade-in animations
const observerOptions = {
  threshold: 0.1,
  rootMargin: "0px 0px -100px 0px",
};

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = "1";
      entry.target.style.transform = "translateY(0)";
    }
  });
}, observerOptions);

document
  .querySelectorAll(".feature-card, .location-card, .stat-item")
  .forEach((el) => {
    el.style.opacity = "0";
    el.style.transform = "translateY(30px)";
    el.style.transition = "opacity 0.6s ease, transform 0.6s ease";
    observer.observe(el);
  });

// Example: Login request to backend
async function login(email, password) {
  const formData = new FormData();
  formData.append("username", email);
  formData.append("password", password);

  const res = await fetch("/token", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    alert("Login failed");
    return;
  }

  const data = await res.json();
  console.log("Logged in:", data);
}

const API_URL = "http://127.0.0.1:8000/auth/register"; // Update with your API URL

const registerBtn = document.getElementById("registerBtn");
const modal = document.getElementById("registrationModal");
const closeBtn = document.getElementById("closeBtn");
const form = document.getElementById("registrationForm");
const submitBtn = document.getElementById("submitBtn");
const message = document.getElementById("message");

// Open modal
registerBtn.addEventListener("click", (e) => {
  e.preventDefault();
  modal.classList.add("active");
});

// Close modal
closeBtn.addEventListener("click", () => {
  modal.classList.remove("active");
  resetForm();
});

// Close on outside click
modal.addEventListener("click", (e) => {
  if (e.target === modal) {
    modal.classList.remove("active");
    resetForm();
  }
});

// Handle form submission
form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const formData = {
    full_name: document.getElementById("fullName").value,
    email: document.getElementById("email").value,
    phone: document.getElementById("phone").value,
    password: document.getElementById("password").value,
    role: document.getElementById("role").value,
  };

  submitBtn.disabled = true;
  submitBtn.textContent = "Registering...";
  hideMessage();

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(formData),
    });

    const data = await response.json();

    if (response.ok) {
      showMessage("Registration successful! Welcome aboard.", "success");
      setTimeout(() => {
        modal.classList.remove("active");
        resetForm();
      }, 2000);
    } else {
      showMessage(
        data.detail || "Registration failed. Please try again.",
        "error"
      );
    }
  } catch (error) {
    showMessage(
      "Network error. Please check your connection and try again.",
      "error"
    );
    console.error("Error:", error);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Register";
  }
});

function showMessage(text, type) {
  message.textContent = text;
  message.className = `message ${type} active`;
}

function hideMessage() {
  message.className = "message";
}

function resetForm() {
  form.reset();
  hideMessage();
}
