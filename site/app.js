let activeHarness = 'all';

document.addEventListener('DOMContentLoaded', async () => {
    try {
        const res = await fetch('leaderboard_data.json');
        const data = await res.json();
        renderHarnessFilters(data);
        renderLeaderboard(data);
        renderStats(data);
    } catch (e) {
        document.getElementById('leaderboard-body').innerHTML = 
            '<tr><td colspan="4">No results yet</td></tr>';
    }
});

function getFilteredModels(data) {
    if (activeHarness === 'all') {
        return data.models || [];
    }
    return (data.harness_models?.[activeHarness]) || [];
}

function renderHarnessFilters(data) {
    const container = document.getElementById('harness-filters');
    const harnesses = data.harnesses || [];

    if (harnesses.length <= 1) {
        container.innerHTML = '';
        return;
    }

    const tabs = [
        { id: 'all', label: 'All', count: data.models?.length || 0 },
        ...harnesses.map(h => ({
            id: h,
            label: h.charAt(0).toUpperCase() + h.slice(1),
            count: data.harness_models?.[h]?.length || 0,
        })),
    ];

    container.innerHTML = tabs.map(tab => {
        const active = tab.id === activeHarness ? ' active' : '';
        return `<button class="harness-tab${active}" onclick="setHarness('${tab.id}')">${tab.label} <span class="tab-count">${tab.count}</span></button>`;
    }).join('');
}

function setHarness(harness) {
    activeHarness = harness;
    fetch('leaderboard_data.json')
        .then(r => r.json())
        .then(data => {
            renderHarnessFilters(data);
            renderLeaderboard(data);
        });
}

function renderLeaderboard(data) {
    const tbody = document.getElementById('leaderboard-body');
    const modelKeys = getFilteredModels(data);
    
    if (!modelKeys?.length) {
        tbody.innerHTML = '<tr><td colspan="4">No results for this harness</td></tr>';
        return;
    }

    tbody.innerHTML = modelKeys.map((mk, i) => {
        const s = data.model_stats[mk];
        const squares = data.exams.map(exam => {
            const result = data.exam_results[exam]?.[mk];
            const passed = result?.passed;
            return `<div class="square ${passed ? 'passed' : 'failed'}"></div>`;
        }).join('');
        const displayName = s.display_name || s.model || mk;
        const colonIdx = displayName.lastIndexOf(':');
        const badge = colonIdx !== -1 ? `<span class="badge">${displayName.slice(colonIdx + 1)}</span>` : '';
        const harness = s.harness ? `<span class="badge harness-badge" title="Harness: ${esc(s.harness)}">${esc(s.harness)}</span>` : '';
        return `
            <tr onclick="window.location.href='detail.html?model_key=${encodeURIComponent(mk)}'" class="clickable">
                <td class="rank">${i + 1}</td>
                <td class="model">${esc(displayName)} ${badge} ${harness}</td>
                <td class="score">${s.passed}/${s.total}<br><small>${s.total_steps}/${s.max_steps} steps</small></td>
                <td class="squares-cell"><div class="squares">${squares}</div></td>
            </tr>
        `;
    }).join('');
}

function renderStats(data) {
    const modelKeys = getFilteredModels(data);
    document.getElementById('total-models').textContent = modelKeys.length;
    document.getElementById('total-exams').textContent = data.total_exams || 0;
    if (data.generated_at) {
        document.getElementById('last-updated').textContent = 
            new Date(data.generated_at).toLocaleDateString();
    }
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
