/**
 * Species Browser for Chimera Seed Vocabulary
 *
 * Loads species from ALA data, allows flagging as meaningful kin,
 * and exports seed vocabulary for Chimera ecology.
 */

const STORAGE_KEY = 'chimera-species-flags';
const NOTES_KEY = 'chimera-species-notes';

let allSpecies = [];
let filteredSpecies = [];
let currentIndex = 0;
let currentFilter = 'all';
let flags = {};  // { scientificName: 'kin' | 'maybe' | 'skip' }
let notes = {};  // { scientificName: 'user notes' }

// Taxon group icons
const TAXON_ICONS = {
    fauna: '🦘',
    flora: '🌿',
    fungi: '🍄'
};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    loadFromStorage();
    await loadSpecies();
    setupKeyboardShortcuts();
    setupFilterButtons();
    renderCurrentSpecies();
    updateSummary();
});

async function loadSpecies() {
    try {
        const response = await fetch('species.json');
        if (!response.ok) {
            throw new Error('species.json not found. Run fetch_species.py first.');
        }
        const data = await response.json();

        allSpecies = data.species || [];

        // Set acknowledgment
        if (data.region?.acknowledgment) {
            document.getElementById('acknowledgment').textContent = data.region.acknowledgment;
        }

        applyFilter(currentFilter);

    } catch (error) {
        document.getElementById('species-card').innerHTML = `
            <div class="loading">
                <p>Could not load species data.</p>
                <p style="margin-top: 1rem; font-size: 0.85rem;">
                    Run the fetch script first:<br>
                    <code style="background: #333; padding: 0.5rem; display: inline-block; margin-top: 0.5rem;">
                        python fetch_species.py --email your@email.com
                    </code>
                </p>
            </div>
        `;
        console.error('Error loading species:', error);
    }
}

function loadFromStorage() {
    try {
        const savedFlags = localStorage.getItem(STORAGE_KEY);
        if (savedFlags) flags = JSON.parse(savedFlags);

        const savedNotes = localStorage.getItem(NOTES_KEY);
        if (savedNotes) notes = JSON.parse(savedNotes);
    } catch (e) {
        console.error('Error loading from storage:', e);
    }
}

function saveToStorage() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(flags));
        localStorage.setItem(NOTES_KEY, JSON.stringify(notes));
    } catch (e) {
        console.error('Error saving to storage:', e);
    }
}

function setupFilterButtons() {
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyFilter(btn.dataset.filter);
        });
    });
}

function applyFilter(filter) {
    currentFilter = filter;

    switch (filter) {
        case 'fauna':
        case 'flora':
        case 'fungi':
            filteredSpecies = allSpecies.filter(s => s.taxon_group === filter);
            break;
        case 'unflagged':
            filteredSpecies = allSpecies.filter(s => !flags[s.scientific_name]);
            break;
        case 'kin':
            filteredSpecies = allSpecies.filter(s => flags[s.scientific_name] === 'kin');
            break;
        case 'maybe':
            filteredSpecies = allSpecies.filter(s => flags[s.scientific_name] === 'maybe');
            break;
        default:
            filteredSpecies = [...allSpecies];
    }

    currentIndex = 0;
    renderCurrentSpecies();
}

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Don't trigger if typing in textarea
        if (e.target.tagName === 'TEXTAREA') return;

        switch (e.key) {
            case '1':
            case 'k':
                flag('kin');
                break;
            case '2':
            case 'm':
                flag('maybe');
                break;
            case '3':
            case 's':
                flag('skip');
                break;
            case 'ArrowLeft':
            case 'h':
                navigate(-1);
                break;
            case 'ArrowRight':
            case 'l':
                navigate(1);
                break;
        }
    });
}

function renderCurrentSpecies() {
    const card = document.getElementById('species-card');

    if (filteredSpecies.length === 0) {
        card.innerHTML = `
            <div class="loading">
                No species match this filter.
            </div>
        `;
        return;
    }

    const species = filteredSpecies[currentIndex];
    const currentFlag = flags[species.scientific_name];
    const currentNotes = notes[species.scientific_name] || '';
    const icon = TAXON_ICONS[species.taxon_group] || '?';

    // Build image element
    let imageHtml;
    if (species.image_url) {
        imageHtml = `<img class="species-image" src="${species.image_url}" alt="${species.common_name}" onerror="this.outerHTML='<div class=\\'species-image placeholder\\'>${icon}</div>'">`;
    } else {
        imageHtml = `<div class="species-image placeholder">${icon}</div>`;
    }

    // Display name (prefer common name)
    const displayName = species.common_name || species.scientific_name || 'Unknown';

    // ALA link
    const alaUrl = `https://bie.ala.org.au/species/${encodeURIComponent(species.scientific_name)}`;

    card.innerHTML = `
        ${imageHtml}
        <h2 class="common-name">${displayName}</h2>
        <p class="scientific-name">${species.scientific_name}</p>
        <div class="taxon-info">
            <span class="taxon-badge">${species.taxon_group}</span>
            ${species.family ? ` · ${species.family}` : ''}
        </div>
        <p class="ala-link"><a href="${alaUrl}" target="_blank">View on Atlas of Living Australia</a></p>

        <textarea
            class="notes-input"
            placeholder="Notes: qualities, felt sense, relationships..."
            rows="2"
            onchange="saveNotes('${species.scientific_name.replace(/'/g, "\\'")}', this.value)"
        >${currentNotes}</textarea>

        <div class="button-row">
            <button class="action-btn btn-kin ${currentFlag === 'kin' ? 'active' : ''}" onclick="flag('kin')">
                Meaningful Kin
            </button>
            <button class="action-btn btn-maybe ${currentFlag === 'maybe' ? 'active' : ''}" onclick="flag('maybe')">
                Maybe
            </button>
            <button class="action-btn btn-skip ${currentFlag === 'skip' ? 'active' : ''}" onclick="flag('skip')">
                Skip
            </button>
        </div>

        <p class="progress">${currentIndex + 1} / ${filteredSpecies.length}</p>

        <div class="nav-row">
            <button class="nav-btn" onclick="navigate(-1)">← Previous</button>
            <button class="nav-btn" onclick="navigate(1)">Next →</button>
        </div>

        <p class="keyboard-hint">
            <kbd>1</kbd>/<kbd>k</kbd> kin ·
            <kbd>2</kbd>/<kbd>m</kbd> maybe ·
            <kbd>3</kbd>/<kbd>s</kbd> skip ·
            <kbd>←</kbd>/<kbd>→</kbd> navigate
        </p>
    `;
}

function flag(value) {
    if (filteredSpecies.length === 0) return;

    const species = filteredSpecies[currentIndex];
    flags[species.scientific_name] = value;
    saveToStorage();
    updateSummary();

    // Auto-advance on flag
    setTimeout(() => navigate(1), 150);
}

function saveNotes(scientificName, value) {
    notes[scientificName] = value;
    saveToStorage();
}

function navigate(delta) {
    if (filteredSpecies.length === 0) return;

    currentIndex += delta;
    if (currentIndex < 0) currentIndex = filteredSpecies.length - 1;
    if (currentIndex >= filteredSpecies.length) currentIndex = 0;

    renderCurrentSpecies();
}

function updateSummary() {
    const kinCount = Object.values(flags).filter(f => f === 'kin').length;
    const maybeCount = Object.values(flags).filter(f => f === 'maybe').length;
    const reviewedCount = Object.keys(flags).length;

    document.getElementById('kin-count').textContent = kinCount;
    document.getElementById('maybe-count').textContent = maybeCount;
    document.getElementById('reviewed-count').textContent = reviewedCount;
}

function exportFlagged() {
    const kinSpecies = allSpecies.filter(s => flags[s.scientific_name] === 'kin');
    const maybeSpecies = allSpecies.filter(s => flags[s.scientific_name] === 'maybe');

    const seedVocabulary = {
        exported_at: new Date().toISOString(),
        country: "Bidjigal Country / Sydney Basin",

        meaningful_kin: kinSpecies.map(s => ({
            common_name: s.common_name,
            scientific_name: s.scientific_name,
            taxon_group: s.taxon_group,
            family: s.family,
            notes: notes[s.scientific_name] || "",
            // Placeholders for manual enrichment
            niche_affinities: [],
            qualities: []
        })),

        maybe_kin: maybeSpecies.map(s => ({
            common_name: s.common_name,
            scientific_name: s.scientific_name,
            taxon_group: s.taxon_group,
            family: s.family,
            notes: notes[s.scientific_name] || ""
        })),

        summary: {
            total_kin: kinSpecies.length,
            total_maybe: maybeSpecies.length,
            total_reviewed: Object.keys(flags).length,
            total_available: allSpecies.length
        }
    };

    // Download as JSON
    const blob = new Blob([JSON.stringify(seedVocabulary, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `seed_vocabulary_${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
