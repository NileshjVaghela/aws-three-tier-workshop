// ========================================
// CloudKida - Main JavaScript
// ========================================

// Configuration - Update this with your EC2 backend URL
const API_BASE_URL = window.API_BASE_URL || 'http://localhost:5000';

// DOM Elements
const navbar = document.getElementById('navbar');
const navToggle = document.getElementById('navToggle');
const navMenu = document.getElementById('navMenu');
const backToTop = document.getElementById('backToTop');
const contactForm = document.getElementById('contactForm');
const apiStatus = document.getElementById('apiStatus');
const filterBtns = document.querySelectorAll('.filter-btn');
const labCards = document.querySelectorAll('.lab-card');

// ========================================
// Navigation
// ========================================

// Scroll effect for navbar
window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }

    // Back to top button
    if (window.scrollY > 300) {
        backToTop.classList.add('visible');
    } else {
        backToTop.classList.remove('visible');
    }
});

// Mobile menu toggle
navToggle.addEventListener('click', () => {
    navMenu.classList.toggle('active');
    navToggle.classList.toggle('active');
});

// Close mobile menu on link click
document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
        navMenu.classList.remove('active');
        navToggle.classList.remove('active');
    });
});

// Active nav link on scroll
const sections = document.querySelectorAll('section[id]');
window.addEventListener('scroll', () => {
    const scrollY = window.pageYOffset;
    sections.forEach(section => {
        const sectionHeight = section.offsetHeight;
        const sectionTop = section.offsetTop - 100;
        const sectionId = section.getAttribute('id');
        const navLink = document.querySelector(`.nav-link[href="#${sectionId}"]`);
        
        if (navLink) {
            if (scrollY > sectionTop && scrollY <= sectionTop + sectionHeight) {
                navLink.classList.add('active');
            } else {
                navLink.classList.remove('active');
            }
        }
    });
});

// ========================================
// Labs Filter
// ========================================
filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        // Update active button
        filterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        const filter = btn.dataset.filter;

        labCards.forEach(card => {
            if (filter === 'all' || card.dataset.category === filter) {
                card.style.display = 'block';
                card.style.animation = 'fadeIn 0.5s ease';
            } else {
                card.style.display = 'none';
            }
        });
    });
});

// ========================================
// Contact Form
// ========================================
contactForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const formMessage = document.getElementById('formMessage');
    const submitBtn = contactForm.querySelector('button[type="submit"]');
    
    const formData = {
        name: document.getElementById('name').value,
        email: document.getElementById('email').value,
        subject: document.getElementById('subject').value,
        message: document.getElementById('message').value
    };

    // Disable button during submission
    submitBtn.disabled = true;
    submitBtn.innerHTML = 'Sending... <i class="fas fa-spinner fa-spin"></i>';

    try {
        const response = await fetch(`${API_BASE_URL}/api/contact`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        if (response.ok) {
            formMessage.className = 'form-message success';
            formMessage.textContent = data.message || 'Message sent successfully! We will get back to you soon.';
            contactForm.reset();
        } else {
            formMessage.className = 'form-message error';
            formMessage.textContent = data.error || 'Something went wrong. Please try again.';
        }
    } catch (error) {
        formMessage.className = 'form-message error';
        formMessage.textContent = 'Unable to connect to server. Please try again later.';
    }

    submitBtn.disabled = false;
    submitBtn.innerHTML = 'Send Message <i class="fas fa-paper-plane"></i>';

    // Hide message after 5 seconds
    setTimeout(() => {
        formMessage.className = 'form-message';
    }, 5000);
});

// ========================================
// API Health Check
// ========================================
async function checkApiHealth() {
    const statusDot = apiStatus.querySelector('.status-dot');
    const statusText = apiStatus.querySelector('.status-text');

    try {
        const response = await fetch(`${API_BASE_URL}/api/health`);
        const data = await response.json();

        if (response.ok) {
            statusDot.className = 'status-dot connected';
            statusText.textContent = `Backend: Connected (v${data.version || '1.0'})`;
        } else {
            statusDot.className = 'status-dot disconnected';
            statusText.textContent = 'Backend: Error';
        }
    } catch (error) {
        statusDot.className = 'status-dot disconnected';
        statusText.textContent = 'Backend: Disconnected';
    }
}

// Check API health on load and every 30 seconds
checkApiHealth();
setInterval(checkApiHealth, 30000);

// ========================================
// Animations
// ========================================

// Fade in animation for elements
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Observe elements with animation
document.querySelectorAll('.about-card, .service-card, .lab-card, .priority-card, .team-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(30px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(el);
});

// Counter animation for stats
function animateCounter(element, target) {
    let current = 0;
    const increment = target / 50;
    const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
            element.textContent = target + '+';
            clearInterval(timer);
        } else {
            element.textContent = Math.floor(current) + '+';
        }
    }, 30);
}

// Animate stats when hero is visible
const heroObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const studentCount = document.getElementById('studentCount');
            if (studentCount && !studentCount.dataset.animated) {
                animateCounter(studentCount, 1098);
                studentCount.dataset.animated = 'true';
            }
        }
    });
}, { threshold: 0.5 });

const heroSection = document.querySelector('.hero');
if (heroSection) {
    heroObserver.observe(heroSection);
}

// CSS animation keyframe
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
`;
document.head.appendChild(style);
