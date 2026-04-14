document.addEventListener('DOMContentLoaded', () => {
    console.log("Quest Script Initializing...");

    // --- State ---
    const API_BASE = "http://127.0.0.1:5000";
    let currentSessionId = null;
    let myActorId = null;
    let pendingFlow = null;   // "host" or "join"
    let pendingInviteCode = null;
    let selectedRole = null;

    // --- Element refs ---
    const screens        = document.querySelectorAll('.screen');
    const actionInput    = document.getElementById('actionInput');
    const sendBtn        = document.getElementById('sendBtn');
    const storyBox       = document.getElementById('story');
    const beginBtn       = document.getElementById('beginBtn');
    const charNameInput  = document.getElementById('charNameInput');

    // --- Screen navigation ---
    function showScreen(id) {
        screens.forEach(s => s.classList.remove('active'));
        const target = document.getElementById(id);
        if (target) target.classList.add('active');

        if (id === 'game') loadGameScreen();
    }

    async function loadGameScreen() {
        if (!currentSessionId) return;
        const data = await apiRequest(`/session/${currentSessionId}/state`);
        if (!data) return;
        if (data.game_state) renderGameState(data.game_state);
        const narration = data.game_state?.adventure?.story_flags?.opening_narration;
        if (narration) addMessage('Dungeon Master', narration);
    }

    // Simple nav for data-go buttons with no logic attached
    document.addEventListener('click', e => {
        const btn = e.target.closest('[data-go]');
        if (btn) showScreen(btn.getAttribute('data-go'));
    });

    // --- API helper ---
    async function apiRequest(endpoint, method = 'GET', body = null) {
        try {
            const options = {
                method,
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
            };
            if (body) options.body = JSON.stringify(body);
            const response = await fetch(`${API_BASE}${endpoint}`, options);
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Server error');
            return data;
        } catch (err) {
            console.error('API error:', err);
            addMessage('System', `Error: ${err.message}`);
            return null;
        }
    }

    // --- Auth ---
    document.getElementById('loginBtn').addEventListener('click', async () => {
        const username = document.getElementById('loginUser').value.trim();
        const password = document.getElementById('loginPass').value;
        if (!username || !password) return alert('Enter username and password.');
        const data = await apiRequest('/auth/login', 'POST', { username, password });
        if (data) {
            showScreen('dashboard');
        }


    });

    document.getElementById('registerBtn').addEventListener('click', async () => {
        const username = document.getElementById('regUser').value.trim();
        const email    = document.getElementById('regEmail').value.trim();
        const password = document.getElementById('regPass').value;
        if (!username || !password) return alert('Enter username and password.');
        const data = await apiRequest('/auth/register', 'POST', { username, email, password });
        if (data) {
            alert('Account created! Please log in.');
            showScreen('login');
        }
    });

    document.getElementById('logoutBtn').addEventListener('click', async () => {
        await apiRequest('/auth/logout', 'POST');
        currentSessionId = null;
        myActorId = null;
        showScreen('login');
    });

    // --- New game flow ---
    document.getElementById('hostBtn').addEventListener('click', () => {
        pendingFlow = 'host';
        pendingInviteCode = null;
        selectedRole = null;
        charNameInput.value = '';
        updateBeginBtn();
        showScreen('characters');
    });

    document.getElementById('joinNavBtn').addEventListener('click', () => {
        showScreen('join');
    });

    document.getElementById('joinNavToCharsBtn').addEventListener('click', () => {
        const code = document.getElementById('joinCodeInput').value.trim();
        if (!code) return alert('Enter a game code.');
        pendingFlow = 'join';
        pendingInviteCode = code;
        selectedRole = null;
        charNameInput.value = '';
        updateBeginBtn();
        showScreen('characters');
    });

    // --- Character selection ---
    document.getElementById('classSelection').addEventListener('click', e => {
        const card = e.target.closest('.class-card');
        if (!card) return;
        document.querySelectorAll('.class-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        selectedRole = card.dataset.class;
        updateBeginBtn();
    });

    charNameInput.addEventListener('input', updateBeginBtn);

    function updateBeginBtn() {
        beginBtn.disabled = !(selectedRole && charNameInput.value.trim());
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

    // --- NEW: Handle Initial Narration for the Host ---
    // If the story box is empty (hardcoded text removed), 
    // show the DM's opening scene description.
    if (storyBox.children.length === 0 && state.scene.description_seed) {
        addMessage("Dungeon Master", state.scene.description_seed);
    document.getElementById('beginBtn').addEventListener('click', async () => {
        const charName = charNameInput.value.trim();
        if (!selectedRole || !charName) return;

        if (pendingFlow === 'host') {
            const data = await apiRequest('/session/create', 'POST', {
                character_name: charName,
                role: selectedRole,
            });
            if (data) {
                currentSessionId = data.session_id;
                myActorId = 'player_1';
                document.getElementById('hostCode').innerText = data.invite_code;
                document.getElementById('hostPlayerCount').innerText = 'Waiting for Players: 1/2';
                showScreen('host');
            }
        } else if (pendingFlow === 'join') {
            const data = await apiRequest('/session/join', 'POST', {
                invite_code: pendingInviteCode,
                character_name: charName,
                role: selectedRole,
            });
            if (data) {
                currentSessionId = data.session_id;
                myActorId = 'player_2';
                showScreen('game');
            }
        }
    });

    document.getElementById('cancelHostBtn').addEventListener('click', async () => {
        if (currentSessionId) {
            await apiRequest(`/session/${currentSessionId}/end`, 'POST');
            currentSessionId = null;
        }
        showScreen('newgame');
    });

    // --- Game screen ---
    document.getElementById('exitGameBtn').addEventListener('click', async () => {
        if (currentSessionId) {
            await apiRequest(`/session/${currentSessionId}/end`, 'POST');
            currentSessionId = null;
        }
        showScreen('dashboard');
    });

    function renderGameState(gs) {
        // Player stats
        const me = gs.entities && gs.entities[myActorId];
        if (me) {
            document.getElementById('stat-hp').innerText = `HP: ${me.hp}/${me.max_hp}`;
            document.getElementById('stat-mp').innerText = `MP: ${me.mp}/${me.max_mp}`;
            if (me.weapon) {
                document.getElementById('inventory-weapon').innerText = `• ${me.weapon.name}`;
            }
        }

        // Round number
        document.getElementById('round-number').innerText = gs.round_number || 1;

        // Turn indicator
        const currentActor = gs.initiative_order && gs.initiative_order[gs.current_turn_index];
        const isMyTurn = currentActor === myActorId;
        const turnEl = document.getElementById('turn-indicator');
        if (gs.in_combat) {
            turnEl.innerText = isMyTurn ? 'Your Turn!' : `Waiting: ${currentActor}`;
            turnEl.style.color = isMyTurn ? '#4ade80' : '#94a3b8';
        } else {
            turnEl.innerText = '';
        }
        actionInput.disabled = !isMyTurn;
        sendBtn.disabled = !isMyTurn;
        actionInput.placeholder = isMyTurn ? 'Your turn! Describe your action...' : 'Waiting for others...';

        // Enemy list
        const enemyList = document.getElementById('enemy-list');
        const placeholder = document.getElementById('enemy-placeholder');
        const enemies = Object.values(gs.entities || {}).filter(e => e.type === 'enemy' && e.hp > 0);
        // Remove old enemy entries (keep the h3 and placeholder)
        enemyList.querySelectorAll('.enemy-entry').forEach(el => el.remove());
        if (enemies.length > 0) {
            if (placeholder) placeholder.style.display = 'none';
            enemies.forEach(enemy => {
                const div = document.createElement('div');
                div.className = 'enemy-entry';
                const pct = Math.max(0, Math.round((enemy.hp / enemy.max_hp) * 100));
                div.innerHTML = `
                    <p style="margin:4px 0; font-size:13px;">${enemy.id} (${enemy.role})</p>
                    <div style="background:#1e293b; border-radius:3px; height:6px; width:100%;">
                        <div style="background:#ef4444; height:6px; border-radius:3px; width:${pct}%;"></div>
                    </div>
                    <p style="font-size:11px; opacity:0.6; margin:2px 0;">${enemy.hp}/${enemy.max_hp} HP</p>`;
                enemyList.appendChild(div);
            });
        } else if (placeholder) {
            placeholder.style.display = '';
        }
    }
}

    // --- Action submission ---
    async function handlePlayerAction() {
        const text = actionInput.value.trim();
        if (!text || !currentSessionId) return;

        addMessage('You', text);
        actionInput.value = '';
        actionInput.disabled = true;
        sendBtn.disabled = true;

        const result = await apiRequest(`/session/${currentSessionId}/action`, 'POST', {
            actor_id: myActorId,
            action_description: text,
        });

        if (!result) return;

        if (result.message) addMessage('Dungeon Master', result.message);
        if (result.game_state) renderGameState(result.game_state);

        if (result.session_over) {
            const outcome = result.winner ? 'Victory! Your party triumphed.' : 'Defeat. Your party has fallen.';
            addMessage('Dungeon Master', outcome);
            actionInput.disabled = true;
            sendBtn.disabled = true;
            actionInput.placeholder = 'Game over.';

            // Show return button
            const returnBtn = document.createElement('button');
            returnBtn.innerText = 'Return to Dashboard';
            returnBtn.style.marginTop = '10px';
            returnBtn.addEventListener('click', () => {
                currentSessionId = null;
                showScreen('dashboard');
            });
            storyBox.parentElement.appendChild(returnBtn);
        }
    }

    sendBtn.addEventListener('click', handlePlayerAction);
    actionInput.addEventListener('keypress', e => { if (e.key === 'Enter') handlePlayerAction(); });

    function addMessage(sender, text) {
        const p = document.createElement('p');
        p.innerHTML = `<b>${sender}:</b> ${text}`;
        storyBox.appendChild(p);
        storyBox.scrollTop = storyBox.scrollHeight;
    }

    // --- Init ---
    showScreen('login');
});
