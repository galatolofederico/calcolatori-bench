document.addEventListener('DOMContentLoaded', async () => {
    const params = new URLSearchParams(window.location.search);
    const modelName = params.get('model');
    
    if (!modelName) {
        window.location.href = 'index.html';
        return;
    }

    try {
        const res = await fetch('leaderboard_data.json');
        const data = await res.json();
        
        if (!data.models?.includes(modelName)) {
            window.location.href = 'index.html';
            return;
        }
        
        renderHeader(modelName, data);
        renderExams(modelName, data);
    } catch (e) {
        document.getElementById('exams-container').innerHTML = '<p class="error">Failed to load results</p>';
    }
});

function renderHeader(modelName, data) {
    document.title = `${modelName} - calcolatori-bench`;
    document.getElementById('model-name').textContent = modelName;
    
    const stats = data.model_stats[modelName];
    if (stats) {
        document.getElementById('model-stats').textContent = 
            `${stats.passed}/${stats.total} exams passed (${stats.percentage}%)`;
    }
}

function renderExams(modelName, data) {
    const container = document.getElementById('exams-container');
    const detailed = data.detailed_results?.[modelName];
    
    if (!detailed || !data.exams?.length) {
        container.innerHTML = '<p class="no-data">No exam results available</p>';
        return;
    }

    container.innerHTML = data.exams.map(exam => {
        const result = detailed[exam];
        if (!result) {
            return `
                <div class="exam-card na">
                    <div class="exam-header">
                        <span class="exam-name">${esc(exam)}</span>
                        <span class="exam-status">No result</span>
                    </div>
                </div>
            `;
        }

        const statusClass = result.passed ? 'pass' : 'fail';
        const statusText = result.passed ? 'PASSED' : 'FAILED';

        return `
            <div class="exam-card ${statusClass}">
                <div class="exam-header">
                    <span class="exam-name">${esc(exam)}</span>
                    <div class="exam-meta">
                        ${renderDuration(result.duration_seconds)}
                        <span class="exam-status">${statusText}</span>
                    </div>
                </div>
                <div class="exam-details">
                    ${renderOutputSection('Expected Output', result.expected)}
                    ${renderOutputSection('Actual Output', result.output)}
                    ${renderDiffSection(result.diff)}
                    ${renderBootOutput(result.boot_output)}
                    ${renderAgentOutput(result.agent_output)}
                </div>
            </div>
        `;
    }).join('');
}

function renderDuration(seconds) {
    if (seconds === null || seconds === undefined) {
        return '';
    }
    
    let display;
    if (seconds < 60) {
        display = `${seconds}s`;
    } else if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        display = `${mins}m ${secs}s`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        display = `${hours}h ${mins}m`;
    }
    
    return `<span class="exam-duration">${display}</span>`;
}

function renderOutputSection(title, output) {
    if (!output || (Array.isArray(output) && output.length === 0)) {
        return '';
    }
    
    const content = Array.isArray(output) ? output.join('\n') : output;
    return `
        <div class="detail-section">
            <h4>${title}</h4>
            <pre class="output-block">${esc(content)}</pre>
        </div>
    `;
}

function renderDiffSection(diff) {
    if (!diff) {
        return '';
    }
    return `
        <div class="detail-section">
            <h4>Code Diff</h4>
            <pre class="diff-block">${esc(diff)}</pre>
        </div>
    `;
}

function renderBootOutput(bootOutput) {
    if (!bootOutput) {
        return '';
    }
    return `
        <div class="detail-section collapsible">
            <h4 class="collapsible-header" onclick="toggleCollapse(this)">
                Boot Output <span class="toggle-icon">+</span>
            </h4>
            <pre class="output-block collapsed">${esc(bootOutput)}</pre>
        </div>
    `;
}

function renderAgentOutput(agentOutput) {
    if (!agentOutput) {
        return `
            <div class="detail-section">
                <h4>Agent Output</h4>
                <p class="no-data">Not available yet</p>
            </div>
        `;
    }
    return `
        <div class="detail-section collapsible">
            <h4 class="collapsible-header" onclick="toggleCollapse(this)">
                Agent Output <span class="toggle-icon">+</span>
            </h4>
            <pre class="output-block collapsed">${esc(agentOutput)}</pre>
        </div>
    `;
}

function toggleCollapse(header) {
    const content = header.nextElementSibling;
    const icon = header.querySelector('.toggle-icon');
    
    if (content.classList.contains('collapsed')) {
        content.classList.remove('collapsed');
        icon.textContent = '−';
    } else {
        content.classList.add('collapsed');
        icon.textContent = '+';
    }
}

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
