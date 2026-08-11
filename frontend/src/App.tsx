import { useState, useRef, useEffect } from 'react';
import { Plus, Send, Paperclip, Edit2, Square, ChevronDown, ChevronUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import './index.css';

interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  citations: any[];
  metric: string | null;
  isHallucination?: boolean;
  warningMessage?: string;
}

function App() {
  const [messages, setMessages] = useState<Message[]>([
    { id: 'msg-1', role: 'ai', content: 'Hello! I am your AI Health Assistant. How can I help you today?', citations: [], metric: null },
  ]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editInput, setEditInput] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string>(`sess-${Date.now()}`);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() && images.length === 0) return;
    
    const userMessage = input;
    const userMsgId = crypto.randomUUID();
    setMessages(prev => [...prev, { id: userMsgId, role: 'user', content: userMessage, citations: [], metric: null }]);
    setInput('');
    setImages([]);
    setIsStreaming(true);
    
    // Add placeholder for AI response
    const aiMessageId = crypto.randomUUID();
    setMessages(prev => [...prev, { 
      id: aiMessageId, 
      role: 'ai', 
      content: '', 
      citations: [], 
      metric: null 
    }]);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionIdRef.current, message: userMessage, images: images }),
        signal: abortController.signal
      });
      
      if (!res.ok) throw new Error("Failed to send message");
      
      const reader = res.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      
      if (reader) {
        let aiContent = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");
          
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const dataStr = line.substring(6);
              if (dataStr === "[DONE]") {
                setIsStreaming(false);
                break;
              }
              try {
                const parsed = JSON.parse(dataStr);
                const tokenVal = parsed.token || parsed.content;
                if (tokenVal) {
                  aiContent += tokenVal;
                  setMessages(prev => prev.map(m => m.id === aiMessageId ? { ...m, content: aiContent } : m));
                }
                if (parsed.stage === "verification_complete") {
                    setMessages(prev => prev.map(m => m.id === aiMessageId ? { ...m, metric: `Time-to-verified: ${parsed.time_to_verified || 'N/A'}` } : m));
                }
                if (parsed.type === "hallucination") {
                    setMessages(prev => prev.map(m => m.id === aiMessageId ? { ...m, isHallucination: true, warningMessage: parsed.message, content: parsed.raw_response } : m));
                }
              } catch (e) {
                // Ignore parse errors for incomplete chunks
              }
            }
          }
        }
      }
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        setMessages(prev => prev.map(m => m.id === aiMessageId ? { ...m, content: m.content + "\n[Error generating response]" } : m));
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleEditSave = async (msgId: string) => {
    if (!editInput.trim()) return;
    
    // Find index of the message being edited
    const msgIndex = messages.findIndex(m => m.id === msgId);
    if (msgIndex === -1) return;
    
    // Update locally: truncate history, update message
    const newMessages = messages.slice(0, msgIndex);
    const updatedUserMsg = { ...messages[msgIndex], content: editInput };
    newMessages.push(updatedUserMsg);
    
    // Placeholder for AI
    const aiMessageId = crypto.randomUUID();
    newMessages.push({ id: aiMessageId, role: 'ai', content: '', citations: [], metric: null });
    
    setMessages(newMessages);
    setEditingMessageId(null);
    setIsStreaming(true);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const res = await fetch('/api/chat/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionIdRef.current, message_id: msgId, message: editInput }),
        signal: abortController.signal
      });
      
      if (!res.ok) throw new Error("Failed to edit message");
      
      const reader = res.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      
      if (reader) {
        let aiContent = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");
          
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const dataStr = line.substring(6);
              if (dataStr === "[DONE]") {
                setIsStreaming(false);
                break;
              }
              try {
                const parsed = JSON.parse(dataStr);
                if (parsed.token || parsed.content) {
                  aiContent += (parsed.token || parsed.content);
                  setMessages(prev => prev.map(m => m.id === aiMessageId ? { ...m, content: aiContent } : m));
                }
                if (parsed.stage === "verification_complete") {
                    setMessages(prev => prev.map(m => m.id === aiMessageId ? { ...m, metric: `Time-to-verified: ${parsed.time_to_verified || 'N/A'}` } : m));
                }
                if (parsed.type === "hallucination") {
                    setMessages(prev => prev.map(m => m.id === aiMessageId ? { ...m, isHallucination: true, warningMessage: parsed.message, content: parsed.raw_response } : m));
                }
              } catch (e) {
                // Ignore parse errors for incomplete chunks
              }
            }
          }
        }
      }
    } catch (error: any) {
      if (error.name !== 'AbortError') {
        setMessages(prev => prev.map(m => m.id === aiMessageId ? { ...m, content: m.content + "\n[Error generating response]" } : m));
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
        abortControllerRef.current.abort();
    }
    setIsStreaming(false);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
        const files = Array.from(e.target.files).slice(0, 5 - images.length);
        const base64Promises = files.map(file => {
            return new Promise<string>((resolve, reject) => {
                const reader = new FileReader();
                reader.readAsDataURL(file);
                reader.onload = () => resolve(reader.result as string);
                reader.onerror = error => reject(error);
            });
        });
        try {
            const newImages = await Promise.all(base64Promises);
            setImages(prev => [...prev, ...newImages].slice(0, 5));
        } catch (err) {
            console.error("Error reading files", err);
        }
    }
  };

  const Citation = ({ citation }: { citation: any }) => {
    const [expanded, setExpanded] = useState(false);
    return (
        <div className="citations-box">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <a href={citation.url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-primary)', textDecoration: 'none', fontWeight: 500 }}>{citation.title}</a>
                <button onClick={() => setExpanded(!expanded)} className="icon-btn">
                    {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
            </div>
            {expanded && <div style={{ marginTop: '0.5rem', color: 'var(--text-secondary)' }}>{citation.snippet}</div>}
        </div>
    );
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <button className="new-chat-btn" onClick={() => setMessages([])}>
          <Plus size={18} />
          New Chat
        </button>
        <div className="history-list">
          <div className="history-item active">Current Session</div>
          <div className="history-item">Symptoms of Flu</div>
          <div className="history-item">Diet Guidelines</div>
        </div>
      </aside>

      <main className="main-chat">
        <header className="chat-header">
          <h1>Health Chatbot</h1>
        </header>

        <div className="messages-container">
          {messages.map(msg => (
            <div key={msg.id} className={`message ${msg.role}`}>
              <div className="bubble">
                {editingMessageId === msg.id ? (
                  <div className="edit-container">
                    <textarea 
                      className="edit-input" 
                      value={editInput} 
                      onChange={(e) => setEditInput(e.target.value)} 
                      autoFocus
                    />
                    <div className="edit-actions">
                      <button onClick={() => setEditingMessageId(null)}>Cancel</button>
                      <button className="primary" onClick={() => handleEditSave(msg.id)}>Save & Submit</button>
                    </div>
                  </div>
                ) : (
                  <>
                    {msg.isHallucination && (
                      <div className="hallucination-warning">
                        <strong>Warning:</strong> {msg.warningMessage}
                      </div>
                    )}
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                    {msg.citations && msg.citations.length > 0 && (
                        <div style={{ marginTop: '1rem' }}>
                            {msg.citations.map((cit: any, i: number) => <Citation key={i} citation={cit} />)}
                        </div>
                    )}
                    {msg.metric && <div className="metric">{msg.metric}</div>}
                  </>
                )}
              </div>
              {msg.role === 'user' && editingMessageId !== msg.id && (
                <div className="message-actions">
                  <button className="icon-btn" title="Edit message" onClick={() => {
                    setEditInput(msg.content);
                    setEditingMessageId(msg.id);
                  }}><Edit2 size={14} /></button>
                </div>
              )}
            </div>
          ))}
          {isStreaming && (
            <div className="message ai">
              <div className="bubble">
                <div className="typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          {images.length > 0 && (
            <div className="image-preview-area">
              {images.map((img, idx) => (
                <img key={idx} src={img} alt="upload preview" className="image-preview" />
              ))}
            </div>
          )}
          <div className="input-box">
            <div className="image-upload-wrapper">
              <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="image-upload-input" multiple accept="image/*" disabled={isStreaming} />
              <button className="image-upload-btn" onClick={() => fileInputRef.current?.click()} disabled={isStreaming}>
                <Paperclip size={20} />
              </button>
            </div>
            <textarea
              className="main-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={isStreaming ? 'AI is thinking...' : 'Ask a health question...'}
              disabled={isStreaming}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
            {isStreaming ? (
              <button className="cancel-btn" onClick={handleCancel}>
                <Square size={18} fill="currentColor" />
              </button>
            ) : (
              <button className="send-btn" onClick={handleSend} disabled={!input.trim() && images.length === 0}>
                <Send size={18} />
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
