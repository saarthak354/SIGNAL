// -----------------------------------
// WHERE THE API LIVES
// -----------------------------------
//
// The frontend is static files and the API is a
// separate service, so the address has to come
// from somewhere.
//
// index.html sets window.SIGNAL_API for the
// deployed site. Without it -- opening the page
// on a laptop, or straight off disk -- it falls
// back to the local backend, so development
// needs no configuration and no build step.

const LOCAL_API = "http://127.0.0.1:5050";


// Where the page is being served from decides
// which backend it talks to.
//
// Checking this rather than just reading
// SIGNAL_API, because the deployed index.html
// carries the production URL and that file is
// the same one served by the local dev server.
// Without this, running dev.py would quietly
// talk to the live API -- and be refused by it,
// since its CORS allowlist is the deployed site
// and nothing else.
//
// The empty hostname is file://, which is what
// opening index.html straight off disk gives.

const LOCAL_HOSTS = ["127.0.0.1", "localhost", ""];


function apiBase() {

    if (LOCAL_HOSTS.includes(window.location.hostname)) {
        return LOCAL_API;
    }

    return (window.SIGNAL_API || "").trim() || LOCAL_API;
}


const API = apiBase();

// How many articles a single view shows. Keeps
// every page short enough to reach the footer.
const ARTICLES_PER_PAGE = 15;

// Search is a deliberate act, so it is allowed
// a longer page than a feed you only scroll.
const SEARCH_RESULTS_PER_PAGE = 30;

// Home is a front page, not a feed. Six is what
// the editorial grid below is built around: one
// lead, two beside it, three underneath.
const HOME_ARTICLES_PER_PAGE = 6;

const newsFeed = document.getElementById("news-feed");
const companyList = document.getElementById("company-list");
const articleView = document.getElementById("article-view");
const currentDate = document.getElementById("current-date");
const eyebrow = document.getElementById("eyebrow");
const headline = document.getElementById("headline");

const pager = document.getElementById("pager");

const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const searchClear = document.getElementById("search-clear");


// -----------------------------------
// CURRENT DATE
// -----------------------------------
//
// The line under the headline. Every view but
// search shows today's date; search replaces it
// with the number of things it found.

const today = new Date();

const TODAY = today.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric"
});


function setDateLine(text) {

    currentDate.textContent = text;
}


setDateLine(TODAY);


// -----------------------------------
// VIEW STATE
// -----------------------------------

const state = {
    tab: "home",
    companyId: null,
    companyName: null,
    query: "",
    page: 1,

    // The article being read, and the address to
    // put the reader back on when they leave it
    articleId: null,
    returnTo: null
};


// -----------------------------------
// LIGHT AND DARK
// -----------------------------------
//
// Three states, not two. "light" and "dark" are
// choices; no attribute at all means follow the
// machine, which is what a first-time visitor
// gets and what most people want.
//
// The attribute is already on <html> by the time
// this runs -- index.html sets it inline in the
// head, before the first paint, so the page never
// flashes the wrong theme. This half only handles
// the switching.

const THEME_KEY = "signal-theme";

const themeToggle = document.getElementById("theme-toggle");


function systemPrefersDark() {

    return window.matchMedia
        && window.matchMedia("(prefers-color-scheme: dark)").matches;
}


function currentTheme() {

    const chosen = document.documentElement.getAttribute("data-theme");

    if (chosen === "dark" || chosen === "light") {
        return chosen;
    }

    return systemPrefersDark() ? "dark" : "light";
}


function applyTheme(theme) {

    document.documentElement.setAttribute("data-theme", theme);

    try {
        localStorage.setItem(THEME_KEY, theme);

    } catch (error) {
        // Private browsing. The theme still applies
        // for this visit, it just will not be
        // remembered for the next one.
    }

    describeToggle();
}


// The button's label has to say what it will do,
// not what is currently true, or a screen reader
// announces the opposite of what happens.

function describeToggle() {

    if (!themeToggle) {
        return;
    }

    const next = currentTheme() === "dark" ? "light" : "dark";

    themeToggle.setAttribute("aria-label", `Switch to ${next} mode`);
    themeToggle.setAttribute("title", `Switch to ${next} mode`);
}


if (themeToggle) {

    themeToggle.addEventListener("click", () => {

        applyTheme(currentTheme() === "dark" ? "light" : "dark");
    });

    describeToggle();
}


// Somebody who has never chosen is following the
// system, so the page should keep following it if
// the system changes under them.

if (window.matchMedia) {

    window.matchMedia("(prefers-color-scheme: dark)")
        .addEventListener("change", () => {

            if (!document.documentElement.getAttribute("data-theme")) {
                describeToggle();
            }
        });
}


// -----------------------------------
// STALE RESPONSES
// -----------------------------------
//
// Every view loads over the network, and the
// slowest of them -- opening an article that has
// not been summarised yet -- can take several
// seconds. Long enough to press Back first.
//
// The reply still arrives, and the code that
// handles it writes into elements the whole page
// shares: the headline, the feed, the date line.
// So an article opened and abandoned would put
// its own title where "AI. Without the noise."
// belongs, and stay there until the next reload.
//
// Each navigation takes a number. Anything that
// comes back holding an old one has been
// overtaken, and is dropped rather than drawn.

let navigation = 0;


function beginNavigation() {

    navigation += 1;

    return navigation;
}


function current(token) {

    return token === navigation;
}


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
//   #/search/gpt-5        search results
//   #/article/1234        one article, with its summary
//
// Search lives at its own address like every
// other view, so a set of results can be
// linked, reloaded, and backed out of.
//
// Any of them can carry a page on the end:
//
//   #/p2                  home, second page
//   #/companies/openai/p3
//   #/search/gpt-5/p2
//
// Page one is left off, so the ordinary address
// of a view never grows a suffix.
//
// Hash routing rather than pushState: this
// page is usually opened straight from disk,
// and pushState is blocked on file:// URLs.

const PAGE_PATTERN = /^p(\d+)$/;


// Takes a trailing page marker off the address
// and returns the page it named.
//
// "keep" is how many parts the view itself needs.
// Without it a search for "p2" would read as page
// two of an empty query.

function takePage(parts, keep) {

    const match = PAGE_PATTERN.exec(
        parts[parts.length - 1] || ""
    );

    if (!match || parts.length <= keep) {
        return 1;
    }

    parts.pop();

    return Math.max(1, Number(match[1]));
}


function parseRoute() {

    const parts = window.location.hash
        .replace(/^#\/?/, "")
        .split("/")
        .filter(Boolean);

    if (parts[0] === "article") {

        return {
            tab: "article",
            page: 1,
            companyId: null,
            query: "",
            articleId: parts[1] ? decodeURIComponent(parts[1]) : null
        };
    }

    if (parts[0] === "companies") {

        return {
            tab: "companies",
            page: takePage(parts, 1),
            companyId: parts[1] ? decodeURIComponent(parts[1]) : null,
            query: ""
        };
    }

    if (parts[0] === "discovery") {

        return {
            tab: "discovery",
            page: takePage(parts, 1),
            companyId: null,
            query: ""
        };
    }

    if (parts[0] === "search") {

        return {
            tab: "search",
            page: takePage(parts, 2),
            companyId: null,
            query: parts[1] ? decodeURIComponent(parts[1]) : ""
        };
    }

    return {
        tab: "home",
        page: takePage(parts, 0),
        companyId: null,
        query: ""
    };
}


function routeFor(tab, companyId) {

    if (companyId) {
        return `#/companies/${encodeURIComponent(companyId)}`;
    }

    return tab === "home" ? "#/" : `#/${tab}`;
}


function routeForSearch(query) {

    return `#/search/${encodeURIComponent(query)}`;
}


function routeForArticle(id) {

    return `#/article/${encodeURIComponent(id)}`;
}


function withPage(route, page) {

    if (page <= 1) {
        return route;
    }

    return route === "#/"
        ? `#/p${page}`
        : `${route}/p${page}`;
}


// The address of the view being looked at,
// without its page, so the pager can build
// the one either side of it.

function currentRoute() {

    if (state.tab === "search") {
        return routeForSearch(state.query);
    }

    return routeFor(state.tab, state.companyId);
}


function currentRouteWithPage() {

    return withPage(currentRoute(), state.page);
}


// Searching for what is already on screen leaves
// the address unchanged, and an unchanged address
// fires no hashchange, so redraw it directly.

function navigate(hash) {

    if (window.location.hash === hash) {

        applyRoute();
        return;
    }

    window.location.hash = hash;
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

    // A query is arbitrary text, so it cannot be
    // set at the size the fixed headlines use
    headline.classList.toggle(
        "headline--query",
        state.tab === "search" || state.tab === "article"
    );

    // The eyebrow doubles as the way back, the
    // same as it does on a company page. The
    // headline is filled in once the article is
    // actually here.
    if (state.tab === "article") {

        eyebrow.innerHTML = "";

        const back = document.createElement("a");

        back.className = "back-link";
        back.href = state.returnTo || "#/";
        back.textContent = "\u2190 Back";

        eyebrow.appendChild(back);

        headline.textContent = "";

        setDateLine("");

        return;
    }

    if (state.tab === "search") {

        eyebrow.textContent = "SEARCH";

        headline.textContent = `\u201C${state.query}\u201D`;

        // Replaced with a count once the results
        // are actually back
        setDateLine("");

        return;
    }

    setDateLine(TODAY);

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

    const token = beginNavigation();

    const route = parseRoute();

    // Where "Back" goes: the view being left,
    // remembered before the address changes to
    // the article. Reaching an article from a
    // pasted link has nothing to remember, so
    // that falls back to the feed.
    if (route.tab === "article" && state.tab !== "article") {
        state.returnTo = currentRouteWithPage();
    }

    state.tab = route.tab;
    state.companyId = route.companyId;
    state.query = route.query;
    state.page = route.page;
    state.articleId = route.articleId || null;

    state.companyName = route.companyId
        ? await companyName(route.companyId)
        : null;

    // The company lookup is a network call, so a
    // second navigation can have happened while
    // it was out
    if (!current(token)) {
        return;
    }

    // Whatever the address says is what the box
    // says, so the back button and a pasted link
    // both leave it showing the right thing
    searchInput.value = state.query;

    showClearButton();

    markActiveTab();
    applyHeading();

    window.scrollTo(0, 0);

    if (state.tab === "article") {
        loadArticle();
    }
    else if (state.tab === "companies" && !state.companyId) {
        loadCompanies();
    }
    else {
        loadArticles();
    }

}


window.addEventListener("hashchange", applyRoute);


// -----------------------------------
// THE LOADING STATE
// -----------------------------------
//
// Now that the feed is served from the store,
// most loads finish in single-digit milliseconds.
// Painting "Loading" before every one of them put
// a spinner on screen for a single frame, which
// the eye catches as a flicker and reads as the
// page stuttering -- the opposite of what a
// loading state is for.
//
// So it waits. Anything that answers quickly
// never shows one at all, and anything genuinely
// slow still says so.

const LOADER_DELAY = 150;


function showLoading(element) {

    const timer = setTimeout(() => {

        element.innerHTML = `<p class="loading">Loading\u2026</p>`;

    }, LOADER_DELAY);

    // Called on every way out, including the
    // failures: a loader left armed would land
    // on top of an error message a moment after
    // it was written.
    return () => clearTimeout(timer);
}


// -----------------------------------
// LOAD ARTICLES
// -----------------------------------

function pageSize() {

    if (state.tab === "search") {
        return SEARCH_RESULTS_PER_PAGE;
    }

    // A company's own page is an archive even
    // though it has no tab of its own
    if (state.tab === "home" && !state.companyId) {
        return HOME_ARTICLES_PER_PAGE;
    }

    return ARTICLES_PER_PAGE;
}


function articleQuery() {

    const params = new URLSearchParams();

    if (state.tab === "search") {
        params.set("q", state.query);
    }
    else if (state.companyId) {
        params.set("company", state.companyId);
    }
    else {
        params.set("tab", state.tab);
    }

    const size = pageSize();

    params.set("limit", size);

    const offset = (state.page - 1) * size;

    if (offset) {
        params.set("offset", offset);
    }

    return params;
}


function countLine(total) {

    if (!total) {
        return "No results";
    }

    return total === 1 ? "1 result" : `${total} results`;
}


async function loadArticles() {

    const token = navigation;

    companyList.hidden = true;
    articleView.hidden = true;
    newsFeed.hidden = false;

    // Whatever the last view's pager said is not
    // true of this one until its articles are back
    hidePager();

    const doneLoading = showLoading(newsFeed);

    // A search route with nothing in it is not a
    // search, so send the visitor home instead of
    // asking the server for everything
    if (state.tab === "search" && !state.query.trim()) {

        doneLoading();

        navigate("#/");
        return;
    }

    const url = `${API}/api/articles?${articleQuery()}`;

    try {

        const response = await fetch(url);

        if (!response.ok) {
            throw new Error("Failed to fetch articles");
        }

        const data = await response.json();

        doneLoading();

        if (!current(token)) {
            return;
        }

        if (state.tab === "search") {

            // Before the cap, so the page can say how
            // much it found and not just how much it
            // is willing to show
            setDateLine(countLine(data.total_available));

            displayArticles(
                data.articles,
                "Nothing matched that."
            );
        }
        else {

            displayArticles(data.articles);
        }

        displayPager(
            data.total_available,
            data.articles.length
        );

    } catch (error) {

        console.error("Error loading articles:", error);

        doneLoading();

        if (!current(token)) {
            return;
        }

        hidePager();

        newsFeed.innerHTML = `
            <p class="error">Unable to load articles.</p>
        `;
    }
}


// -----------------------------------
// OPEN ONE ARTICLE
// -----------------------------------
//
// The summary is the page. It is written to be
// complete enough that opening the original is
// a choice rather than the next step, so the
// link to it sits at the bottom, after the
// reading rather than in place of it.


// The summary comes back as Markdown, and it is
// the only HTML on this page that is not written
// here, so it is escaped first and then given
// back exactly the three things the prompt asks
// for: paragraphs, bold and italic. Anything
// else the model emits stays as text.
//
// Escaping before formatting, never after: the
// other way round would let an article title
// containing a tag close one of ours.

function escapeHtml(text) {

    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}


function renderSummary(markdown) {

    return escapeHtml(markdown)
        .split(/\n\s*\n/)
        .map(block => block.trim())
        .filter(Boolean)
        .map(block => {

            const inline = block
                .replace(/\n/g, " ")

                // Bold first: its markers would
                // otherwise read as two italics
                .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
                .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
                .replace(/_([^_\n]+)_/g, "<em>$1</em>");

            return `<p>${inline}</p>`;
        })
        .join("");
}


// What to say when there is no summary, which
// depends on why. None of these are errors the
// reader can do anything about, so none of them
// are dressed up as one.

const NO_SUMMARY = {

    thin:
        "The original page could not be read \u2014 usually a paywall, " +
        "a consent screen, or an article that builds itself in the browser.",

    failed:
        "The summary could not be written this time. It will be retried.",

    pending:
        "No summary yet."
};


function summaryFallback(article) {

    const note = NO_SUMMARY[article.summary_status] || NO_SUMMARY.pending;

    // The blurb is thin, but it is what we have,
    // and it beats an empty page
    const blurb = cleanDescription(article.description);

    return `
        ${blurb ? `<p>${escapeHtml(blurb)}</p>` : ""}
        <p class="summary-note">${note}</p>
    `;
}


function displayArticle(article) {

    headline.textContent = article.title;

    setDateLine(
        [article.source, formatDate(article.published)]
            .filter(Boolean)
            .join("  \u00B7  ")
    );

    const body = article.summary
        ? renderSummary(article.summary)
        : summaryFallback(article);

    const subject = article.category === "discovery"
        ? article.related_company
        : article.company;

    articleView.innerHTML = `

        ${subject ? `<div class="article-subject">${escapeHtml(subject)}</div>` : ""}

        <div class="summary">${body}</div>

        <div class="article-original">

            <a href="${escapeHtml(article.url)}"
               target="_blank"
               rel="noopener noreferrer">
                Read the original at ${escapeHtml(article.source || "the source")}
                <span aria-hidden="true">\u2197</span>
            </a>

        </div>
    `;
}


async function loadArticle() {

    const token = navigation;

    newsFeed.hidden = true;
    companyList.hidden = true;
    articleView.hidden = false;

    hidePager();

    const doneLoading = showLoading(articleView);

    if (!state.articleId) {

        doneLoading();

        navigate("#/");
        return;
    }

    try {

        const response = await fetch(
            `${API}/api/articles/${encodeURIComponent(state.articleId)}`
        );

        doneLoading();

        if (!current(token)) {
            return;
        }

        if (response.status === 404) {

            headline.textContent = "Article not found";

            articleView.innerHTML = `
                <p class="error">
                    That article is no longer in the feed.
                </p>
            `;

            return;
        }

        if (!response.ok) {
            throw new Error("Failed to fetch the article");
        }

        displayArticle((await response.json()).article);

    } catch (error) {

        console.error("Error loading article:", error);

        doneLoading();

        if (!current(token)) {
            return;
        }

        headline.textContent = "";

        articleView.innerHTML = `
            <p class="error">Unable to load this article.</p>
        `;
    }
}


// -----------------------------------
// LOAD COMPANIES
// -----------------------------------

async function loadCompanies() {

    const token = navigation;

    newsFeed.hidden = true;
    articleView.hidden = true;
    companyList.hidden = false;

    hidePager();

    const doneLoading = showLoading(companyList);

    try {

        const companies = await allCompanies();

        doneLoading();

        if (!current(token)) {
            return;
        }

        displayCompanies(companies);

    } catch (error) {

        console.error("Error loading companies:", error);

        doneLoading();

        if (!current(token)) {
            return;
        }

        companyList.innerHTML = `
            <p class="error">Unable to load companies.</p>
        `;
    }
}


// -----------------------------------
// PAGER
// -----------------------------------
//
// A view shows one page at a time so that the
// footer is always within reach, but nothing
// drops off the end: whatever the page does not
// hold is one link away, and both links are real
// addresses, so the back button walks back
// through the pages you came from.

function hidePager() {

    pager.hidden = true;

    pager.innerHTML = "";

    newsFeed.classList.remove("news-feed--paged");
}


function pagerLink(route, label) {

    const link = document.createElement("a");

    link.className = "pager-link";
    link.href = route;
    link.textContent = label;

    return link;
}


// Holds the empty side so the count stays put
// whether or not there is a link beside it

function pagerGap() {

    const gap = document.createElement("span");

    gap.className = "pager-gap";

    return gap;
}


function displayPager(total, shown) {

    // Worked out here rather than read back off the
    // response: this page asked for the offset, so
    // it already knows it, and a reply that is not
    // shaped as expected should still paginate
    const offset = (state.page - 1) * pageSize();

    const hasPrevious = state.page > 1;

    const hasNext = offset + shown < total;

    if (!hasPrevious && !hasNext) {

        hidePager();
        return;
    }

    pager.innerHTML = "";

    const base = currentRoute();

    pager.appendChild(
        hasPrevious
            ? pagerLink(
                withPage(base, state.page - 1),
                "\u2190 Previous"
            )
            : pagerGap()
    );


    const count = document.createElement("span");

    count.className = "pager-count";

    // An address can name a page past the end, so
    // say the total rather than an empty range
    count.textContent = shown
        ? `${offset + 1}\u2013${offset + shown} of ${total}`
        : `${total} in total`;

    pager.appendChild(count);


    // Home is six stories and an invitation. The
    // archives are lists you page through.
    const nextLabel = state.tab === "home" && !state.companyId
        ? "Continue reading \u2192"
        : "Load next \u2192";

    pager.appendChild(
        hasNext
            ? pagerLink(
                withPage(base, state.page + 1),
                nextLabel
            )
            : pagerGap()
    );


    pager.hidden = false;

    newsFeed.classList.add("news-feed--paged");
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
// THE EDITORIAL GRID
// -----------------------------------
//
// Home is not a list. Six stories run as a front
// page would set them: the lead takes two columns
// and the full height beside it, two more stack
// down the right, and three sit along the bottom.
//
//     ┌───────────────┬───────┐
//     │               │   2   │
//     │       1       ├───────┤
//     │               │   3   │
//     ├───────┬───────┼───────┤
//     │   4   │   5   │   6   │
//     └───────┴───────┴───────┘
//
// Only the lead is placed by hand. Everything
// after it falls into the gaps the grid leaves,
// so a short last page still lands correctly.

const EDITORIAL_ROLES = [
    "news-item--lead",
    "news-item--side",
    "news-item--side"
];

const EDITORIAL_DEFAULT_ROLE = "news-item--base";


function editorialRole(index) {

    return EDITORIAL_ROLES[index] || EDITORIAL_DEFAULT_ROLE;
}


// -----------------------------------
// ONE ARTICLE CARD
// -----------------------------------

function createArticle(article, position) {

    const articleElement = document.createElement("article");

    articleElement.classList.add("news-item");


    // -----------------------------------
    // META
    // -----------------------------------

    const meta = document.createElement("div");

    meta.classList.add("article-meta");


    // A running number, so the page reads in an
    // order rather than as six equal things
    if (position !== null) {

        const index = document.createElement("span");

        index.classList.add("article-index");

        index.textContent =
            String(position + 1).padStart(2, "0");

        meta.appendChild(index);
    }


    const source = document.createElement("span");

    source.classList.add("article-source");

    source.textContent = (article.source || "").toUpperCase();


    const time = document.createElement("span");

    time.classList.add("article-time");

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

    // Its own address, so the summary is a page
    // like any other: linkable, reloadable, and
    // backed out of with the browser's own button
    // as well as the one on the page.
    articleElement.addEventListener("click", () => {

        navigate(routeForArticle(article.id));

    });


    return articleElement;
}


// -----------------------------------
// DISPLAY ARTICLES
// -----------------------------------

function displayArticles(articles, emptyMessage) {

    // Home gets the grid. The archives stay a
    // single column, because a list of everything
    // one company published is a list.
    const editorial =
        state.tab === "home" && !state.companyId;

    newsFeed.classList.toggle("news-feed--editorial", editorial);

    newsFeed.innerHTML = "";

    if (!articles.length) {

        const message = document.createElement("p");

        message.className = "error";

        message.textContent =
            emptyMessage || "Nothing here right now.";

        newsFeed.appendChild(message);

        return;
    }

    // The numbering carries on across pages, so
    // page two opens at 07 rather than at 01
    const firstPosition = (state.page - 1) * pageSize();

    articles.forEach((article, index) => {

        const card = createArticle(
            article,
            editorial ? firstPosition + index : null
        );

        if (editorial) {
            card.classList.add(editorialRole(index));
        }

        newsFeed.appendChild(card);

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

    // Never negative. Ingestion clamps dates to
    // the moment they were read, but a visitor's
    // clock can still run ahead of the server's,
    // and "-3m ago" is never the right thing to
    // show someone.
    const difference = Math.max(
        0,
        Math.floor((now - published) / 1000)
    );


    const minutes =
        Math.floor(difference / 60);

    const hours =
        Math.floor(minutes / 60);

    const days =
        Math.floor(hours / 24);


    if (minutes < 1) {
        return "just now";
    }

    if (minutes < 60) {
        return `${minutes}m ago`;
    }

    if (hours < 24) {
        return `${hours}h ago`;
    }

    return `${days}d ago`;
}


// -----------------------------------
// FORMAT DATE
// -----------------------------------
//
// A card says "3h ago", because on a feed what
// matters is how fresh a thing is next to the
// ones around it. An opened article has nothing
// to be compared against, so it gets the date
// it was actually published.

function formatDate(dateString) {

    if (!dateString) {
        return "";
    }

    const published = new Date(dateString);

    if (isNaN(published)) {
        return "";
    }

    return published.toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
        year: "numeric"
    });
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
// SEARCH
// -----------------------------------
//
// The pill in the navbar. Submitting it moves
// to the search route, and everything else on
// the page reacts to that address the same way
// it reacts to any other.

function showClearButton() {

    searchClear.hidden = !searchInput.value;
}


searchInput.addEventListener("input", showClearButton);


searchForm.addEventListener("submit", event => {

    event.preventDefault();

    const query = searchInput.value.trim();

    // Clicking the magnifying glass on an empty
    // box should open the box, not run a search
    if (!query) {

        searchInput.focus();
        return;
    }

    navigate(routeForSearch(query));
});


searchClear.addEventListener("click", () => {

    searchInput.value = "";

    showClearButton();

    searchInput.focus();

    // Clearing the box you searched from should
    // clear the results it produced
    if (state.tab === "search") {
        navigate("#/");
    }
});


searchInput.addEventListener("keydown", event => {

    if (event.key === "Escape") {
        searchInput.blur();
    }
});


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
