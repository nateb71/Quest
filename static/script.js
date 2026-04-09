document.addEventListener('DOMContentLoaded', () => {
    console.log("Quest Script Initializing...");

    // --- Configuration & State ---
    const API_BASE = "http://127.0.0.1:5000"; 
    let currentUser = null;
    let currentSessionId = null;
    let myActorId = null; 
    let pollingInterval = null;

    // --- Elements ---
    const screens = document.querySelectorAll('.screen');
    const actionInput = document.getElementById('actionInput');
    const sendBtn = document.getElementById('sendBtn');
    const storyBox = document.getElementById('story');
    const diceResult = document.getElementById('diceResult');

    // --- Navigation & API Helpers ---
    function showScreen(id) {
        console.log("Navigating to:", id);
        screens.forEach(s => s.classList.remove('active'));
        const target = document.getElementById(id);
        if (target) {
            target.classList.add('active');
        }
        
        if (id === 'game') {
            startPolling();
        } else {
            stopPolling();
        }
    }

    async function apiRequest(endpoint, method = 'GET', body = null) {
        try {
            const options = {
                method,
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include' 
            };
            if (body) options.body = JSON.stringify(body);
            
            const response = await fetch(`${API_BASE}${endpoint}`, options);
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.error || 'Server Error');
            return data;
        } catch (err) {
            console.error("Connection Failed:", err);
            alert("Error: " + err.message);
            return null;
    }
}

// --- Event Delegation (Fixed Selectors) ---
document.addEventListener('click', async (e) => {
        const target = e.target.closest('[data-go]');
        if (!target) return;

        const goTo = target.getAttribute('data-go');

        // Logic for Registering a New Account
        if (goTo === 'login' && target.closest('#register')) {
            const username = target.parentElement.querySelector('input[type="text"]').value;
            const email = target.parentElement.querySelector('input[type="email"]').value; // Optional
            const password = target.parentElement.querySelector('input[type="password"]').value;
            
            const data = await apiRequest('/auth/register', 'POST', { username, password });
            if (data && !data.error) {
                alert("Account created! Please log in.");
                showScreen('login');
            }
            return;
        }

        // Logic for Login
        if (goTo === 'dashboard' && target.closest('#login')) {
            const username = document.getElementById('loginUser').value;
            const password = document.getElementById('loginPass').value;
            const data = await apiRequest('/auth/login', 'POST', { username, password });
            if (data) {
                currentUser = data;
                showScreen('dashboard');
            }
            return;
        }

        // Logic for Hosting
        if (goTo === 'host') {
            const charName = prompt("Enter your character's name:");
            const role = prompt("Choose role (warrior, rogue, mage):").toLowerCase();
            const data = await apiRequest('/session/create', 'POST', { character_name: charName, role: role });
            if (data) {
                currentSessionId = data.session_id;
                myActorId = "player_1";
                document.querySelector('#host .code-box').innerText = data.invite_code;
                showScreen('host');
            }
            return;
        }

        // Logic for Joining
        if (goTo === 'characters' && target.closest('#join')) {
            const code = document.querySelector('#join input').value;
            const charName = prompt("Enter your character's name:");
            const role = prompt("Choose role (warrior, rogue, mage):").toLowerCase();
            const data = await apiRequest('/session/join', 'POST', { invite_code: code, character_name: charName, role: role });
            if (data) {
                currentSessionId = data.session_id;
                myActorId = "player_2";
                showScreen('game');
                updateGameState();
            }
            return;
        }

        // Default navigation for everything else
        showScreen(goTo);
    });

    // --- Game Engine Hooks ---
    async function updateGameState() {
        if (!currentSessionId) return;
        const data = await apiRequest(`/session/${currentSessionId}/state`);
        if (data) renderGame(data.game_state);
    }

    function renderGame(state) {
        const me = state.entities[myActorId];
        if (!me) return;
        document.getElementById('stat-hp').innerText = `HP: ${me.hp}/${me.max_hp}`;
        document.getElementById('stat-mp').innerText = `MP: ${me.mp}/${me.max_mp}`;
        const currentTurnActor = state.initiative_order[state.current_turn_index];
        const isMyTurn = currentTurnActor === myActorId;
        sendBtn.disabled = !isMyTurn;
        actionInput.placeholder = isMyTurn ? "Your turn! Describe action..." : "Waiting for others...";
    }

    async function handlePlayerAction() {
        const text = actionInput.value.trim();
        if (!text || !currentSessionId) return;
        addMessage("You", text);
        actionInput.value = '';
        const result = await apiRequest(`/session/${currentSessionId}/action`, 'POST', {
            actor_id: myActorId,
            action_type: "attack", // Defaulting to attack for now
            target_id: "goblin_1", // You'll need to update this to be dynamic later
            action_name: "standard_action"
        });
        if (result && result.message) {
            addMessage("Dungeon Master", result.message);
            renderGame(result.game_state);
        }
    }

    function addMessage(sender, text) {
        const p = document.createElement('p');
        p.innerHTML = `<b>${sender}:</b> ${text}`;
        storyBox.appendChild(p);
        storyBox.scrollTop = storyBox.scrollHeight;
    }

    function startPolling() { if (!pollingInterval) pollingInterval = setInterval(updateGameState, 3000); }
    function stopPolling() { clearInterval(pollingInterval); pollingInterval = null; }

    sendBtn.addEventListener('click', handlePlayerAction);
    actionInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handlePlayerAction(); });

    // --- Safety Initialization ---
    showScreen('login');
});