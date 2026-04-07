document.addEventListener('DOMContentLoaded', () => {
    // --- Elements ---
    const screens = document.querySelectorAll('.screen');
    const actionInput = document.getElementById('actionInput');
    const sendBtn = document.getElementById('sendBtn');
    const storyBox = document.getElementById('story');
    const diceResult = document.getElementById('diceResult');

    // --- Navigation System ---
    // Handles all buttons with [data-go="screenName"]
    document.addEventListener('click', (e) => {
        const target = e.target.closest('[data-go]');
        if (target) {
            const screenId = target.getAttribute('data-go');
            showScreen(screenId);
        }
    });

    function showScreen(id) {
        screens.forEach(s => s.classList.remove('active'));
        document.getElementById(id).classList.add('active');
    }

    // --- Character Selection ---
    const classCards = document.querySelectorAll('.class-card');
    classCards.forEach(card => {
        card.addEventListener('click', () => {
            classCards.forEach(c => c.style.border = 'none');
            card.style.border = '2px solid #6366f1';
            const selectedClass = card.getAttribute('data-class');
            console.log("Selected Class:", selectedClass);
            // Integration Point: Save selected class to a global state or database
        });
    });

    // --- Dice System ---
document.querySelectorAll('.dice').forEach(die => {
    die.addEventListener('click', () => {
        const sides = die.getAttribute('data-roll');
        const roll = Math.floor(Math.random() * sides) + 1;
        
        // 1. Remove the animation class (if it exists) to reset it
        diceResult.classList.remove('roll-animation');
        
        // 2. Void offset trick to force a DOM reflow (triggers animation restart)
        void diceResult.offsetWidth; 
        
        // 3. Update text and re-add the animation class
        diceResult.innerHTML = `<strong>D${sides} rolled: ${roll}</strong>`;
        diceResult.classList.add('roll-animation');
        
        // Log to story
        addMessage("System", `You rolled a D${sides}: ${roll}`);
    });
});

    // --- Story & Integration ---
    function addMessage(sender, text) {
        const p = document.createElement('p');
        p.innerHTML = `<b>${sender}:</b> ${text}`;
        storyBox.appendChild(p);
        storyBox.scrollTop = storyBox.scrollHeight;
    }

    function handlePlayerAction() {
        const text = actionInput.value.trim();
        if (!text) return;

        addMessage("You", text);
        actionInput.value = '';

        // Integration Point: This is where you would call an AI API
        // For now, we simulate a delay
        setTimeout(() => {
            addMessage("Dungeon Master", `The wind howls as you attempt to "${text}". What do you do next?`);
        }, 600);
    }

    sendBtn.addEventListener('click', handlePlayerAction);
    actionInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handlePlayerAction();
    });
});