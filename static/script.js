document.addEventListener('DOMContentLoaded', () => {
    console.log("Quest Script Initializing...");

    // ── State ────────────────────────────────────────────────────────────────
    const API_BASE = window.location.origin;
    let currentSessionId = null;
    let myActorId        = null;
    let pendingFlow      = null;   // "host" or "join"
    let pendingInviteCode = null;
    let selectedRole     = null;

    // ── Socket.IO connection ─────────────────────────────────────────────────
    // Connect once on page load; the server keeps the connection alive.
    const socket = io(API_BASE, { withCredentials: true });

    socket.on("connect", () => {
        console.log("WebSocket connected:", socket.id);
    });

    socket.on("disconnect", () => {
        console.log("WebSocket disconnected");
        addMessage("System", "Connection lost. Please refresh.");
    });

    // Server-sent error messages
    socket.on("error", ({ message }) => {
        console.error("Socket error:", message);
        addMessage("System", `Error: ${message}`);
    });

    // ── Element refs ─────────────────────────────────────────────────────────
    const screens       = document.querySelectorAll('.screen');
    const actionInput   = document.getElementById('actionInput');
    const sendBtn       = document.getElementById('sendBtn');
    const storyBox      = document.getElementById('story');
    const beginBtn      = document.getElementById('beginBtn');
    const charNameInput = document.getElementById('charNameInput');

    const PUBLIC_SCREENS = new Set(['login', 'register']);

    // ── Screen navigation ────────────────────────────────────────────────────
    function showScreen(id) {
        screens.forEach(s => s.classList.remove('active'));
        const target = document.getElementById(id);
        if (target) target.classList.add('active');
        if (window.location.hash !== `#${id}`) {
            history.pushState({ screen: id }, '', `#${id}`);
        }
        if (id === 'game') _onEnterGameScreen();
    }

    window.addEventListener('popstate', async () => {
        const id = window.location.hash.slice(1) || 'login';
        if (!PUBLIC_SCREENS.has(id)) {
            const user = await apiRequest('/auth/me');
            if (!user) { showScreen('login'); return; }
        }
        if (id === 'game') _restoreGameSession();
        showScreen(id);
    });

    function _onEnterGameScreen() {
        // Nothing to fetch — state arrives via WebSocket events.
        // Re-enable input in case it was locked from a previous session.
        actionInput.disabled = false;
        sendBtn.disabled = false;
    }

    // Simple nav for data-go buttons with no logic attached
    document.addEventListener('click', e => {
        const btn = e.target.closest('[data-go]');
        if (btn) showScreen(btn.getAttribute('data-go'));
    });

    // ── HTTP helper (auth + session setup only) ──────────────────────────────
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

    // ── Auth (stays HTTP) ────────────────────────────────────────────────────
    document.getElementById('loginBtn').addEventListener('click', async () => {
        const username = document.getElementById('loginUser').value.trim();
        const password = document.getElementById('loginPass').value;
        if (!username || !password) return alert('Enter username and password.');
        const data = await apiRequest('/auth/login', 'POST', { username, password });
        if (data) showScreen('dashboard');
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
        localStorage.removeItem('quest_session_id');
        localStorage.removeItem('quest_actor_id');
        showScreen('login');
    });

    // ── New game flow ────────────────────────────────────────────────────────
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

    // ── Character selection ──────────────────────────────────────────────────
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

    // ── Begin Adventure button ───────────────────────────────────────────────
    document.getElementById('beginBtn').addEventListener('click', async () => {
        const charName = charNameInput.value.trim();
        if (!selectedRole || !charName) return;

        if (pendingFlow === 'host') {
            // 1. Create the session via HTTP (one-shot — returns invite code)
            const data = await apiRequest('/session/create', 'POST', {
                character_name: charName,
                role: selectedRole,
            });
            if (!data) return;

            currentSessionId = data.session_id;
            myActorId = 'player_1';
            _saveGameSession(currentSessionId, myActorId);
            document.getElementById('hostCode').innerText = data.invite_code;
            document.getElementById('hostPlayerCount').innerText = 'Waiting for Players: 1/2';

            // 2. Join the WS room so we receive the game_start broadcast
            socket.emit("join_session_room", { session_id: currentSessionId });

            showScreen('host');

        } else if (pendingFlow === 'join') {
            // 1. Join via HTTP (triggers game_start broadcast to host)
            const data = await apiRequest('/session/join', 'POST', {
                invite_code: pendingInviteCode,
                character_name: charName,
                role: selectedRole,
            });
            if (!data) return;

            currentSessionId = data.session_id;
            myActorId = 'player_2';
            _saveGameSession(currentSessionId, myActorId);

            // 2. Join the WS room
            socket.emit("join_session_room", { session_id: currentSessionId });

            // 3. Render the initial state we got back from the HTTP response
            showScreen('game');
            if (data.game_state)        renderGameState(data.game_state);
            if (data.opening_narration) addMessage('Dungeon Master', data.opening_narration);
        }
    });

    // ── WebSocket: game_start (received by the HOST when player 2 joins) ─────
    socket.on("game_start", (data) => {
        console.log("game_start received", data);
        currentSessionId = data.session_id;
        showScreen('game');
        if (data.game_state)        renderGameState(data.game_state);
        if (data.opening_narration) addMessage('Dungeon Master', data.opening_narration);
    });

    // ── Cancel hosting ───────────────────────────────────────────────────────
    document.getElementById('cancelHostBtn').addEventListener('click', () => {
        if (currentSessionId) {
            socket.emit("end_session", { session_id: currentSessionId });
            currentSessionId = null;
        }
        showScreen('newgame');
    });

    // ── Game screen ──────────────────────────────────────────────────────────
    document.getElementById('exitGameBtn').addEventListener('click', () => {
        if (currentSessionId) {
            socket.emit("end_session", { session_id: currentSessionId });
            currentSessionId = null;
        }
        showScreen('dashboard');
    });

    // ── WebSocket: action_result (broadcast to both players after any action) ─
    socket.on("action_result", (result) => {
        if (result.message)    addMessage('Dungeon Master', result.message);
        if (result.game_state) renderGameState(result.game_state);

        if (result.session_over) {
            localStorage.removeItem('quest_session_id');
            localStorage.removeItem('quest_actor_id');
            const outcome = result.winner
                ? 'Victory! Your party triumphed.'
                : 'Defeat. Your party has fallen.';
            addMessage('Dungeon Master', outcome);
            actionInput.disabled = true;
            sendBtn.disabled = true;
            actionInput.placeholder = 'Game over.';

            const returnBtn = document.createElement('button');
            returnBtn.innerText = 'Return to Dashboard';
            returnBtn.style.marginTop = '10px';
            returnBtn.addEventListener('click', () => {
                currentSessionId = null;
                showScreen('dashboard');
            });
            storyBox.parentElement.appendChild(returnBtn);
        }
    });

    // ── WebSocket: session_ended (other player quit) ──────────────────────────
    socket.on("session_ended", ({ message }) => {
        localStorage.removeItem('quest_session_id');
        localStorage.removeItem('quest_actor_id');
        addMessage('System', message || 'The session has ended.');
        actionInput.disabled = true;
        sendBtn.disabled = true;
        actionInput.placeholder = 'Session ended.';
    });

    // ── Render helpers ───────────────────────────────────────────────────────
    function renderGameState(gs) {
        const me = gs.entities && gs.entities[myActorId];
        if (me) {
            document.getElementById('stat-hp').innerText = `HP: ${me.hp}/${me.max_hp}`;
            document.getElementById('stat-mp').innerText = `MP: ${me.mp}/${me.max_mp}`;
            if (me.weapon) {
                document.getElementById('inventory-weapon').innerText = `• ${me.weapon.name}`;
            }
        }

        document.getElementById('round-number').innerText = gs.round_number || 1;

        const currentActor = gs.initiative_order && gs.initiative_order[gs.current_turn_index];
        const turnEl = document.getElementById('turn-indicator');
        let isMyTurn;
        if (gs.in_combat) {
            isMyTurn = currentActor === myActorId;
            const currentEntity = gs.entities && gs.entities[currentActor];
            const actorName = (currentEntity && currentEntity.character_name) || currentActor;
            turnEl.innerText = isMyTurn ? 'Your Turn!' : `Waiting: ${actorName}`;
            turnEl.style.color = isMyTurn ? '#4ade80' : '#94a3b8';
        } else {
            // Combat hasn't started yet — player_1 sends the first action to kick things off
            isMyTurn = myActorId === 'player_1';
            turnEl.innerText = isMyTurn ? 'Start the adventure!' : 'Waiting for player 1 to begin...';
            turnEl.style.color = isMyTurn ? '#4ade80' : '#94a3b8';
        }
        actionInput.disabled = !isMyTurn;
        sendBtn.disabled = !isMyTurn;
        actionInput.placeholder = isMyTurn
            ? 'Describe your action...'
            : 'Waiting for others...';

        const enemyList   = document.getElementById('enemy-list');
        const placeholder = document.getElementById('enemy-placeholder');
        const enemies = Object.values(gs.entities || {}).filter(e => e.type === 'enemy' && e.hp > 0);
        enemyList.querySelectorAll('.enemy-entry').forEach(el => el.remove());
        if (enemies.length > 0) {
            if (placeholder) placeholder.style.display = 'none';
            enemies.forEach(enemy => {
                const div = document.createElement('div');
                div.className = 'enemy-entry';
                const pct = Math.max(0, Math.round((enemy.hp / enemy.max_hp) * 100));
                div.innerHTML = `
                    <p style="margin:4px 0; font-size:13px;">${enemy.character_name || enemy.id} (${enemy.role})</p>
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

    // ── Action submission (now via WebSocket) ─────────────────────────────────
    function handlePlayerAction() {
        const text = actionInput.value.trim();
        if (!text || !currentSessionId) return;

        addMessage('You', text);
        actionInput.value = '';
        // Disable while we wait — re-enabled when action_result arrives
        actionInput.disabled = true;
        sendBtn.disabled = true;

        socket.emit("submit_action", {
            session_id:         currentSessionId,
            actor_id:           myActorId,
            action_description: text,
        });
    }

    sendBtn.addEventListener('click', handlePlayerAction);
    actionInput.addEventListener('keypress', e => {
        if (e.key === 'Enter') handlePlayerAction();
    });

    function addMessage(sender, text) {
        const p = document.createElement('p');
        p.innerHTML = `<b>${sender}:</b> ${text}`;
        storyBox.appendChild(p);
        storyBox.scrollTop = storyBox.scrollHeight;
    }

    // ── Game session persistence ──────────────────────────────────────────────
    function _saveGameSession(sessionId, actorId) {
        localStorage.setItem('quest_session_id', sessionId);
        localStorage.setItem('quest_actor_id', actorId);
    }

    function _restoreGameSession() {
        if (!currentSessionId) {
            currentSessionId = parseInt(localStorage.getItem('quest_session_id'));
            myActorId = localStorage.getItem('quest_actor_id');
            if (currentSessionId) {
                socket.emit('join_session_room', { session_id: currentSessionId });
            }
        }
    }

    // ── Init ─────────────────────────────────────────────────────────────────
    async function _initApp() {
        const hash = window.location.hash.slice(1);
        const user = await apiRequest('/auth/me');
        if (user) {
            const target = (hash && !PUBLIC_SCREENS.has(hash)) ? hash : 'dashboard';
            if (target === 'game') _restoreGameSession();
            showScreen(target);
        } else {
            showScreen('login');
        }
    }
    _initApp();
});