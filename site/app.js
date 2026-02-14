document.addEventListener('DOMContentLoaded', async () => {
    try {
        const response = await fetch('leaderboard_data.json');
        if (!response.ok) throw new Error('Failed to load data');
        const data = await response.json();
        renderStats(data);
        renderLeaderboard(data);
        renderDetailedResults(data);
    } catch (error) {
        console.error('Error loading leaderboard data:', error);
        document.getElementById('leaderboard-body').innerHTML = 
            '<tr><td colspan="4" style="text-align:center">No results available yet</td></tr>';
    }
});

function renderStats(data) {
    document.getElementById('total-models').textContent = data.total_models || 0;
    document.getElementById('total-exams').textContent = data.total_exams || 0;
    
    if (data.generated_at) {
        const date = new Date(data.generated_at);
        document.getElementById('last-updated').textContent = date.toLocaleDateString();
    }
}

function renderLeaderboard(data) {
    const tbody = document.getElementById('leaderboard-body');
    tbody.innerHTML = '';

    if (!data.models || data.models.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center">No results available yet</td></tr>';
        return;
    }

    data.models.forEach((model, index) => {
        const stats = data.model_stats[model];
        const rank = index + 1;
        const row = document.createElement('tr');
        
        row.innerHTML = `
            <td class="rank">#${rank}</td>
            <td class="model-name">${escapeHtml(model)}</td>
            <td class="score-pass">${stats.passed}/${stats.total}</td>
            <td>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${stats.percentage}%"></div>
                </div>
                <span style="margin-left: 10px;">${stats.percentage}%</span>
            </td>
        `;
        
        tbody.appendChild(row);
    });
}

function renderDetailedResults(data) {
    const thead = document.getElementById('results-header');
    const tbody = document.getElementById('results-body');
    
    thead.innerHTML = '';
    tbody.innerHTML = '';

    if (!data.models || data.models.length === 0 || !data.exams || data.exams.length === 0) {
        tbody.innerHTML = '<tr><td style="text-align:center">No detailed results available</td></tr>';
        return;
    }

    const headerRow = document.createElement('tr');
    headerRow.innerHTML = '<th>Model</th>';
    data.exams.forEach(exam => {
        headerRow.innerHTML += `<th>${escapeHtml(exam)}</th>`;
    });
    headerRow.innerHTML += '<th>Total</th>';
    thead.appendChild(headerRow);

    data.models.forEach(model => {
        const row = document.createElement('tr');
        row.innerHTML = `<td class="model-name">${escapeHtml(model)}</td>`;
        
        let passed = 0;
        let total = 0;
        
        data.exams.forEach(exam => {
            const result = data.exam_results[exam]?.[model];
            total++;
            if (result?.passed === true) {
                passed++;
                row.innerHTML += '<td class="pass-icon">&#10004;</td>';
            } else if (result?.passed === false) {
                row.innerHTML += '<td class="fail-icon">&#10008;</td>';
            } else {
                row.innerHTML += '<td class="na-icon">—</td>';
            }
        });
        
        row.innerHTML += `<td class="score-pass">${passed}/${total}</td>`;
        tbody.appendChild(row);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
