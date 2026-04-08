<template>
  <div class="query-view">
    <div class="page-header">
      <div>
        <h1>💬 智能问答</h1>
        <p class="subtitle">基于已收录的新闻库进行 RAG 检索增强回答</p>
      </div>
    </div>

    <!-- 对话区域 -->
    <div class="chat-container card">
      <div class="chat-messages" ref="messagesRef">
        <div v-if="!messages.length" class="chat-welcome">
          <div class="welcome-icon">🤖</div>
          <h2>你好，我是 Logos 新闻助手</h2>
          <p>我可以根据已收录的新闻为你分析和回答问题</p>
          <div class="suggestion-chips">
            <button
              v-for="q in suggestions"
              :key="q"
              class="btn btn-sm"
              @click="askQuestion(q)"
            >{{ q }}</button>
          </div>
        </div>

        <div
          v-for="(msg, i) in messages"
          :key="i"
          :class="['chat-message', msg.role]"
        >
          <div class="message-avatar">
            {{ msg.role === 'user' ? '👤' : '🤖' }}
          </div>
          <div class="message-content">
            <div v-if="msg.role === 'assistant'" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
            <div v-else>{{ msg.content }}</div>
          </div>
        </div>

        <!-- 流式加载中 -->
        <div v-if="streaming" class="chat-message assistant">
          <div class="message-avatar">🤖</div>
          <div class="message-content">
            <div class="markdown-body" v-html="renderMarkdown(streamContent)"></div>
            <span class="typing-cursor">▊</span>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="chat-input-area">
        <input
          v-model="input"
          class="input chat-input"
          placeholder="请输入你的问题，例如：今天有什么重要新闻？"
          @keyup.enter="askQuestion(input)"
          :disabled="streaming"
        />
        <button
          class="btn btn-primary"
          @click="askQuestion(input)"
          :disabled="!input.trim() || streaming"
        >
          {{ streaming ? '回答中...' : '发送' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { queryApi } from '../api'
import { marked } from 'marked'

const messages = ref([])
const input = ref('')
const streaming = ref(false)
const streamContent = ref('')
const messagesRef = ref(null)

const suggestions = [
  '今天有什么重要新闻？',
  '最近 AI 领域有什么进展？',
  '总结一下今天的国际新闻',
]

function renderMarkdown(text) {
  if (!text) return ''
  try {
    return marked(text)
  } catch {
    return `<p>${text}</p>`
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

async function askQuestion(question) {
  if (!question?.trim()) return

  const q = question.trim()
  input.value = ''

  // 添加用户消息
  messages.value.push({ role: 'user', content: q })
  scrollToBottom()

  // 流式请求
  streaming.value = true
  streamContent.value = ''

  try {
    const response = await queryApi.askStream(q)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') {
            break
          }
          if (data.startsWith('[ERROR]')) {
            streamContent.value += '\n\n❌ ' + data.slice(8)
            break
          }
          streamContent.value += data
          scrollToBottom()
        }
      }
    }

    // 完成后将流式内容转为正式消息
    messages.value.push({ role: 'assistant', content: streamContent.value })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `❌ 请求失败: ${e.message}\n\n请检查后端服务是否正常运行。`,
    })
  } finally {
    streaming.value = false
    streamContent.value = ''
    scrollToBottom()
  }
}
</script>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 180px);
  min-height: 500px;
  padding: 0;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  gap: var(--space-md);
  color: var(--text-secondary);
}
.welcome-icon {
  font-size: 4rem;
  margin-bottom: var(--space-sm);
}
.chat-welcome h2 {
  color: var(--text-primary);
}
.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  justify-content: center;
  margin-top: var(--space-md);
}

.chat-message {
  display: flex;
  gap: var(--space-md);
  max-width: 85%;
  animation: messageIn 0.3s ease;
}
.chat-message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.chat-message.assistant {
  align-self: flex-start;
}

@keyframes messageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-avatar {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  flex-shrink: 0;
  background: var(--bg-card);
  border-radius: 50%;
}

.message-content {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-md) var(--space-lg);
  font-size: 0.9375rem;
  line-height: 1.7;
}
.chat-message.user .message-content {
  background: var(--accent-glow);
  border-color: rgba(245, 158, 11, 0.2);
}

.typing-cursor {
  display: inline-block;
  color: var(--accent-primary);
  animation: blink 1s infinite;
}
@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.chat-input-area {
  display: flex;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--border-color);
  background: var(--bg-secondary);
}
.chat-input {
  flex: 1;
}
</style>
