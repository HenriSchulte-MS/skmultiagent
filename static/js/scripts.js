// Configuration of marked to be safe
marked.setOptions({
    sanitize: true,
    breaks: true
});
function loadConversationHistory() {
    $.get("/get_history", function(data) {
        let chatBox = $("#chat-box");
        chatBox.html("");
        data.forEach(msg => {
            const messageClass = msg.role.toLowerCase() === 'user' ? 'user-message' : 'received-message';
            let icon = 'fa-user';
            
            // Assign specific icons according to the role
            switch(msg.role.toLowerCase()) {
                case 'user':
                    icon = 'fa-user';
                    break;
                case 'assistant':
                    icon = 'fa-robot';
                    break;
                case 'expert':
                    icon = 'fa-brain';
                    break;
                case 'researcher':
                    icon = 'fa-microscope';
                    break;
                case 'agent':
                    icon = 'fa-android';
                    break;
                default:
                    icon = 'fa-comment';
            }
            chatBox.append(`
                <div class="message-wrapper ${messageClass}-wrapper">
                    <div class="message ${messageClass}" data-agent="${msg.role}">
                        <div class="message-icon">
                            <i class="fas ${icon}"></i>
                        </div>
                        <div class="message-content">
                            <div class="message-header">${msg.role}</div>
                            <div class="message-text">${marked.parse(msg.message)}</div>
                        </div>
                    </div>
                </div>
            `);
        });
        chatBox.scrollTop(chatBox[0].scrollHeight);
    });
}
function loadEventLog() {
    $.get("/get_events", function(data) {
        let eventList = $("#event-list");
        eventList.html("");
        data.forEach(event => {
            let icon = 'fa-info-circle';
            if (event.event.toLowerCase().includes('conversation')) {
                icon = 'fa-comments';
            } else if (event.event.toLowerCase().includes('agent')) {
                icon = 'fa-robot';
            } else if (event.event.toLowerCase().includes('thread')) {
                icon = 'fa-thread';
            }
            eventList.append(`
                <li class='list-group-item event-item'>
                    <i class="fas ${icon}"></i>
                    <strong>${event.event}:</strong> 
                    <span>${event.details}</span>
                </li>
            `);
        });
    });
}
function sendMessage() {
    let message = $("#user-message").val();
    if (message.trim() === "") return;
    
    let chatBox = $("#chat-box");
    chatBox.append(`
        <div class="message-wrapper user-message-wrapper">
            <div class="message user-message" data-agent="User">
                <div class="message-content">
                    <div class="message-text">${marked.parse(message)}</div>
                </div>
            </div>
        </div>
    `);
    chatBox.scrollTop(chatBox[0].scrollHeight);
    $("#user-message").val("");
    
    $.ajax({
        url: "/send_message",
        type: "POST",
        contentType: "application/json",
        data: JSON.stringify({ message: message }),
        success: function(response) {
            chatBox.append(`
                <div class="message-wrapper received-message-wrapper">
                    <div class="message received-message" data-agent="Agent">
                        <div class="message-icon">
                            <i class="fas fa-robot"></i>
                        </div>
                        <div class="message-content">
                            <div class="message-header">Agent</div>
                            <div class="message-text">${marked.parse(response.response)}</div>
                        </div>
                    </div>
                </div>
            `);
            chatBox.scrollTop(chatBox[0].scrollHeight);
            loadEventLog();
        },
        error: function(xhr, status, error) {
            console.error("Error sending message:", error);
        }
    });
}
function loadConversations() {
    $.get("/get_conversations", function(data) {
        let conversationList = $("#conversation-list");
        conversationList.html("");
        data.forEach(conversation => {
            conversationList.append(`
                <li class='list-group-item conversation-item' onclick='loadConversation("${conversation.id}")'>
                    <i class="fas fa-comments"></i> ${conversation.name || 'Unnamed Conversation'}
                </li>
            `);
        });
    });
}
function loadConversation(conversationId) {
    $.post("/load_conversation", JSON.stringify({ conversation_id: conversationId }), function(data) {
        let chatBox = $("#chat-box");
        chatBox.html("");
        data.messages.forEach(msg => {
            const messageClass = msg.role.toLowerCase() === 'user' ? 'user-message' : 'received-message';
            let icon = 'fa-user';
            
            // Assign specific icons according to the role
            switch(msg.role.toLowerCase()) {
                case 'user':
                    icon = 'fa-user';
                    break;
                case 'assistant':
                    icon = 'fa-robot';
                    break;
                case 'expert':
                    icon = 'fa-brain';
                    break;
                case 'researcher':
                    icon = 'fa-microscope';
                    break;
                case 'agent':
                    icon = 'fa-android';
                    break;
                default:
                    icon = 'fa-comment';
            }
            chatBox.append(`
                <div class="message-wrapper ${messageClass}-wrapper">
                    <div class="message ${messageClass}" data-agent="${msg.role}">
                        <div class="message-icon">
                            <i class="fas ${icon}"></i>
                        </div>
                        <div class="message-content">
                            <div class="message-header">${msg.role}</div>
                            <div class="message-text">${marked.parse(msg.message)}</div>
                        </div>
                    </div>
                </div>
            `);
        });
        chatBox.scrollTop(chatBox[0].scrollHeight);
    });
}
$(document).ready(function() {
    loadConversations();
    loadConversationHistory();
    loadEventLog();
    
    $("#user-message").keypress(function(event) {
        if (event.which === 13) {
            event.preventDefault();
            sendMessage();
        }
    });
});
