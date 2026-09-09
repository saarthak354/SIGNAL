const API = "http://127.0.0.1:5050";

// How many articles a single view shows. Keeps
// every page short enough to reach the footer.
const ARTICLES_PER_PAGE = 15;

const newsFeed = document.getElementById("news-feed");
const companyList = document.getElementById("company-list");
const currentDate = document.getElementById("current-date");
const eyebrow = document.getElementById("eyebrow");
const headline = document.getElementById("headline");


// -----------------------------------
// CURRENT DATE
// -----------------------------------

const today = new Date();

currentDate.textContent = today.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric"
});


// -----------------------------------
// VIEW STATE
// -----------------------------------

const state = {
    tab: "home",
    companyId: null,
    companyName: null
};


// -----------------------------------
// ROUTES
// -----------------------------------
//
// Every view has its own address, so the
// browser's back and forward buttons move
// between them, and any page can be linked
// to or reloaded without losing your place.
//
//   #/                    home
//   #/companies           the company list
//   #/companies/openai    one company
//   #/discovery           discovery
//
// Hash routing rather than pushState: this
// page is usually opened straight from disk,
// and pushState is blocked on file:// URLs.

function parseRoute() {

    const parts = window.location.hash
        .replace(/^#\/?/, "")
        .split("/")
        .filter(Boolean);

    if (parts[0] === "companies") {

        return {
            tab: "companies",
            companyId: parts[1] ? decodeURIComponent(parts[1]) : null
        };
    }

    if (parts[0] === "discovery") {
        return { tab: "discovery", companyId: null };
    }

    return { tab: "home", companyId: null };
}


function routeFor(tab, companyId) {

    if (companyId) {
        return `#/companies/${encodeURIComponent(companyId)}`;
    }

    return tab === "home" ? "#/" : `#/${tab}`;
}


// -----------------------------------
// COMPANY LOOKUP
// -----------------------------------
//
// Cached so that landing directly on a
// company page can still name it.

let companyCache = null;


async function allCompanies() {

    if (!companyCache) {

        const response = await fetch(`${API}/api/companies`);

        if (!response.ok) {
            throw new Error("Failed to fetch companies");
        }

        companyCache = (await response.json()).companies;
    }

    return companyCache;
}


async function companyName(id) {

    try {

        const found = (await allCompanies())
            .find(company => company.id === id);

        // Never echo an unknown id back as a
        // headline; it came from the address bar
        return found ? found.name : null;

    } catch (error) {

        return null;
    }
}


// -----------------------------------
// HEADINGS PER VIEW
// -----------------------------------

function setHeading(label, title) {

    eyebrow.textContent = label;

    headline.innerHTML = title;
}


function applyHeading() {

    if (state.companyId) {

        // The label doubles as the way back
        eyebrow.innerHTML = "";

        const back = document.createElement("a");

        back.className = "back-link";
        back.href = routeFor("companies");
        back.textContent = "\u2190 All companies";

        eyebrow.appendChild(back);

        headline.textContent =
            state.companyName || "Company not found";

        return;
    }

    if (state.tab === "companies") {

        setHeading(
            "COMPANIES",
            "Straight from<br>the source."
        );

        return;
    }

    if (state.tab === "discovery") {

        setHeading(
            "DISCOVERY",
            "Everything else<br>worth reading."
        );

        return;
    }

    setHeading(
        "WHATS NEW",
        "AI.<br>Without the noise."
    );
}


// -----------------------------------
// NAVIGATION
// -----------------------------------
//
// The nav items are ordinary links now, so
// the browser handles history for us.

const navLinks = document.querySelectorAll(".navbar nav a");


function markActiveTab() {

    navLinks.forEach(link => {

        // A company page still belongs to Companies
        link.classList.toggle(
            "active",
            link.dataset.tab === state.tab
        );

    });

}


async function applyRoute() {

    const route = parseRoute();

    state.tab = route.tab;
    state.companyId = route.companyId;

    state.companyName = route.companyId
        ? await companyName(route.companyId)
        : null;

    markActiveTab();
    applyHeading();

    window.scrollTo(0, 0);

    if (state.tab === "companies" && !state.companyId) {
        loadCompanies();
    }
    else {
        loadArticles();
    }

}


window.addEventListener("hashchange", applyRoute);


// -----------------------------------
// LOAD ARTICLES
// -----------------------------------

async function loadArticles() {

    companyList.hidden = true;
    newsFeed.hidden = false;

    newsFeed.innerHTML = `<p class="loading">Loading…</p>`;

    const query = state.companyId
        ? `?company=${encodeURIComponent(state.companyId)}`
        : `?tab=${encodeURIComponent(state.tab)}`;

    const url = `${API}/api/articles${query}&limit=${ARTICLES_PER_PAGE}`;

    try {

        const response = await fetch(url);

        if (!response.ok) {
            throw new Error("Failed to fetch articles");
        }

        const data = await response.json();

        displayArticles(data.articles);

    } catch (error) {

        console.error("Error loading articles:", error);

        newsFeed.innerHTML = `
            <p class="error">Unable to load articles.</p>
        `;
    }
}


// -----------------------------------
// LOAD COMPANIES
// -----------------------------------

async function loadCompanies() {

    newsFeed.hidden = true;
    companyList.hidden = false;

    companyList.innerHTML = `<p class="loading">Loading…</p>`;

    try {

        displayCompanies(await allCompanies());

    } catch (error) {

        console.error("Error loading companies:", error);

        companyList.innerHTML = `
            <p class="error">Unable to load companies.</p>
        `;
    }
}


// -----------------------------------
// DISPLAY COMPANIES
// -----------------------------------

function displayCompanies(companies) {

    companyList.innerHTML = "";

    companies.forEach(company => {

        const row = document.createElement("a");

        row.classList.add("company-item");

        // A real link, so it lands in history and
        // can be opened in a new tab
        row.href = routeFor("companies", company.id);


        // -----------------------------------
        // LOGO
        // -----------------------------------
        //
        // Brand marks arrive with every kind of
        // background, so each one sits on the same
        // tile. If the file is missing the tile
        // falls back to the company's initial.

        const identity = document.createElement("div");

        identity.classList.add("company-identity");


        const logo = document.createElement("span");

        logo.classList.add("company-logo");


        const mark = document.createElement("img");

        mark.src = `logos/${company.id}.png`;
        mark.alt = "";

        mark.addEventListener("error", () => {

            mark.remove();

            logo.classList.add("company-logo--fallback");

            logo.textContent = company.name.charAt(0);
        });

        logo.appendChild(mark);


        const name = document.createElement("h2");

        name.textContent = company.name;


        identity.appendChild(logo);
        identity.appendChild(name);


        const meta = document.createElement("span");

        meta.classList.add("company-count");

        meta.textContent = company.count === 1
            ? "1 article"
            : `${company.count} articles`;


        row.appendChild(identity);
        row.appendChild(meta);


        companyList.appendChild(row);

    });

}


// -----------------------------------
// DISPLAY ARTICLES
// -----------------------------------

function displayArticles(articles) {

    newsFeed.innerHTML = "";

    if (!articles.length) {

        newsFeed.innerHTML = `
            <p class="error">Nothing here right now.</p>
        `;

        return;
    }

    articles.forEach(article => {

        const articleElement = document.createElement("article");

        articleElement.classList.add("news-item");


        // -----------------------------------
        // META
        // -----------------------------------

        const meta = document.createElement("div");

        meta.classList.add("article-meta");


        const source = document.createElement("span");

        source.textContent = (article.source || "").toUpperCase();


        const time = document.createElement("span");

        time.textContent = formatTime(article.published);


        meta.appendChild(source);
        meta.appendChild(time);


        // -----------------------------------
        // TITLE
        // -----------------------------------

        const title = document.createElement("h2");

        title.textContent = article.title;


        // -----------------------------------
        // DESCRIPTION
        // -----------------------------------

        const description = document.createElement("p");

        description.textContent = cleanDescription(article.description);


        // -----------------------------------
        // CATEGORY
        // -----------------------------------

        // On a company page the source line already
        // names the company, so only add a chip when
        // it says something the card does not.

        const category = document.createElement("div");

        category.classList.add("article-category");

        const via = article.via || "";

        if (article.category === "discovery") {

            // The meta line names the exact site this
            // came from; this names who it is about.
            // Both are kept even when they agree, which
            // happens when an aggregator links straight
            // to a company's own blog.
            category.textContent = article.related_company
                ? article.related_company
                : `Via ${via}`;

            if (category.textContent === `Via ${source.textContent}`) {
                category.textContent = "";
            }
        }
        else {

            category.textContent = article.company || "";

            // On a company card this only ever repeats
            // the source line
            if (category.textContent.toUpperCase() === source.textContent) {
                category.textContent = "";
            }
        }


        articleElement.appendChild(meta);
        articleElement.appendChild(title);

        if (description.textContent) {
            articleElement.appendChild(description);
        }

        if (category.textContent) {
            articleElement.appendChild(category);
        }


        // -----------------------------------
        // CLICK ARTICLE
        // -----------------------------------

        articleElement.addEventListener("click", () => {

            window.open(
                article.url,
                "_blank"
            );

        });


        newsFeed.appendChild(articleElement);

    });

}


// -----------------------------------
// FORMAT TIME
// -----------------------------------

function formatTime(dateString) {

    if (!dateString) {
        return "";
    }

    const published = new Date(dateString);

    if (isNaN(published)) {
        return "";
    }

    const now = new Date();

    const difference =
        Math.floor((now - published) / 1000);


    const minutes =
        Math.floor(difference / 60);

    const hours =
        Math.floor(minutes / 60);

    const days =
        Math.floor(hours / 24);


    if (minutes < 60) {
        return `${minutes}m ago`;
    }

    if (hours < 24) {
        return `${hours}h ago`;
    }

    return `${days}d ago`;
}


// -----------------------------------
// CLEAN RSS DESCRIPTION
// -----------------------------------

function cleanDescription(description) {

    if (!description) {
        return "";
    }

    const temp = document.createElement("div");

    temp.innerHTML = description;

    return temp.textContent || temp.innerText || "";
}


// -----------------------------------
// CONTACT FORM
// -----------------------------------
//
// Feedback and source suggestions are filled in
// on the page and posted to the backend, so the
// visitor is never handed off to a mail client.

const modal = document.getElementById("contact-modal");
const modalTitle = document.getElementById("modal-title");
const contactForm = document.getElementById("contact-form");
const fieldName = document.getElementById("field-name");
const fieldMessage = document.getElementById("field-message");
const messageLabel = document.getElementById("field-message-label");
const formStatus = document.getElementById("form-status");
const submitButton = document.getElementById("modal-submit");


const FORMS = {

    feedback: {
        title: "Send feedback",
        label: "Feedback",
        placeholder: "What is working, and what is not?"
    },

    source: {
        title: "Suggest a source",
        label: "Source",
        placeholder: "Which site or feed should we follow, and why?"
    }

};


let activeForm = "feedback";


function setStatus(text, kind) {

    formStatus.textContent = text;

    formStatus.className = kind
        ? `form-status form-status--${kind}`
        : "form-status";
}


function openForm(type) {

    activeForm = FORMS[type] ? type : "feedback";

    const config = FORMS[activeForm];

    modalTitle.textContent = config.title;
    messageLabel.textContent = config.label;
    fieldMessage.placeholder = config.placeholder;

    contactForm.reset();

    setStatus("");

    submitButton.disabled = false;
    submitButton.textContent = "Send";

    modal.showModal();

    fieldName.focus();
}


function closeForm() {

    if (modal.open) {
        modal.close();
    }
}


document.querySelectorAll(".footer-action").forEach(button => {

    button.addEventListener("click", () => {

        openForm(button.dataset.form);
    });

});


document.getElementById("modal-close")
    .addEventListener("click", closeForm);

document.getElementById("modal-cancel")
    .addEventListener("click", closeForm);


// Clicking the dimmed area closes the form
modal.addEventListener("click", event => {

    if (event.target === modal) {
        closeForm();
    }

});


contactForm.addEventListener("submit", async event => {

    event.preventDefault();

    const name = fieldName.value.trim();
    const message = fieldMessage.value.trim();

    if (!name) {
        setStatus("Please add your name.", "error");
        fieldName.focus();
        return;
    }

    if (!message) {
        setStatus("Please add a message.", "error");
        fieldMessage.focus();
        return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Sending…";

    setStatus("");

    try {

        const response = await fetch(`${API}/api/submissions`, {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                type: activeForm,
                name: name,
                message: message
            })

        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Something went wrong.");
        }

        setStatus("Thanks. We got it.", "ok");

        contactForm.reset();

        submitButton.textContent = "Sent";

        setTimeout(closeForm, 1200);

    } catch (error) {

        console.error("Submission failed:", error);

        setStatus(
            "Could not send that. Please try again.",
            "error"
        );

        submitButton.disabled = false;
        submitButton.textContent = "Send";
    }

});


// -----------------------------------
// START
// -----------------------------------

applyRoute();
