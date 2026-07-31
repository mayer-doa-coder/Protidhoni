import {useCallback, useEffect, useRef, useState} from 'react';
import {FlatList, Pressable, StyleSheet, View} from 'react-native';

import {getAppDatabase} from '../db/appDatabase';
import {listAllReports} from '../db/queue';
import {useLanguage} from '../i18n/LanguageContext';
import {
  askAboutPriorities,
  getLocalAssistant,
  prioritizeReports,
  sendChatMessage,
  type AssistantStatus,
  type ChatMessage,
} from '../llm/localAssistant';
import {AppText, AppTextInput} from '../ui/AppText';

type DisplayMessage = ChatMessage & {id: string};

let messageCounter = 0;
function nextId(): string {
  messageCounter += 1;
  return `m${messageCounter}`;
}

export function ChatScreen() {
  const {t} = useLanguage();
  const [status, setStatus] = useState<AssistantStatus>({state: 'idle'});
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const streamingIdRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStatus({state: 'preparing', detail: t('chat.preparing')});
    getLocalAssistant(next => {
      if (!cancelled) setStatus(next);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once; status callback stays fresh via setStatus
  }, []);

  const appendToken = useCallback((token: string) => {
    const id = streamingIdRef.current;
    if (!id) return;
    setMessages(current =>
      current.map(message =>
        message.id === id ? {...message, content: message.content + token} : message,
      ),
    );
  }, []);

  const send = useCallback(
    async (question: string, usePriorities: boolean) => {
      if (question.trim().length === 0 || sending) return;
      setSending(true);
      setDraft('');
      const userMessage: DisplayMessage = {id: nextId(), role: 'user', content: question};
      const assistantId = nextId();
      streamingIdRef.current = assistantId;
      setMessages(current => [
        ...current,
        userMessage,
        {id: assistantId, role: 'assistant', content: ''},
      ]);

      try {
        if (usePriorities) {
          const db = await getAppDatabase();
          const reports = await listAllReports(db);
          await askAboutPriorities(question, reports, appendToken);
        } else {
          const history = [...messages, userMessage].map(
            ({role, content}): ChatMessage => ({role, content}),
          );
          await sendChatMessage(history, appendToken);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setMessages(current =>
          current.map(entry =>
            entry.id === assistantId ? {...entry, content: t('chat.error', {message})} : entry,
          ),
        );
      } finally {
        streamingIdRef.current = null;
        setSending(false);
      }
    },
    [appendToken, messages, sending, t],
  );

  const askPriorities = useCallback(() => {
    // eslint-disable-next-line no-void -- Pressable's onPress isn't awaited
    void send(t('chat.priorityQuestion'), true);
  }, [send, t]);

  const ready = status.state === 'ready';

  return (
    <View style={styles.page}>
      <AppText style={styles.caveat}>{t('chat.caveat')}</AppText>
      {status.state !== 'ready' && (
        <View style={styles.statusBanner}>
          <AppText style={styles.statusText}>
            {status.state === 'error'
              ? t('chat.loadFailed', {message: status.message})
              : status.state === 'preparing'
                ? status.detail
                : t('chat.preparing')}
          </AppText>
        </View>
      )}
      <FlatList
        contentContainerStyle={styles.messageList}
        data={messages}
        keyExtractor={item => item.id}
        renderItem={({item}) => (
          <View
            style={[
              styles.bubble,
              item.role === 'user' ? styles.userBubble : styles.assistantBubble,
            ]}>
            <AppText
              style={item.role === 'user' ? styles.userBubbleText : styles.assistantBubbleText}>
              {item.content || '…'}
            </AppText>
          </View>
        )}
        ListEmptyComponent={<AppText style={styles.empty}>{t('chat.empty')}</AppText>}
      />
      <Pressable
        disabled={!ready || sending}
        onPress={askPriorities}
        style={[styles.priorityButton, (!ready || sending) && styles.buttonDisabled]}>
        <AppText style={styles.priorityButtonText}>{t('chat.priorityButton')}</AppText>
      </Pressable>
      <View style={styles.composer}>
        <AppTextInput
          accessibilityLabel={t('chat.inputPlaceholder')}
          editable={ready && !sending}
          onChangeText={setDraft}
          placeholder={t('chat.inputPlaceholder')}
          style={styles.input}
          value={draft}
          multiline
        />
        <Pressable
          disabled={!ready || sending || draft.trim().length === 0}
          onPress={() => {
            // eslint-disable-next-line no-void -- Pressable's onPress isn't awaited
            void send(draft, false);
          }}
          style={[
            styles.sendButton,
            (!ready || sending || draft.trim().length === 0) && styles.buttonDisabled,
          ]}>
          <AppText style={styles.sendButtonText}>{t('chat.send')}</AppText>
        </Pressable>
      </View>
    </View>
  );
}

// Exported for potential reuse (e.g. a future "top priority" home-screen card)
// without duplicating the deterministic ranking rule.
export {prioritizeReports};

const styles = StyleSheet.create({
  page: {flex: 1, backgroundColor: '#071a2c'},
  caveat: {
    color: '#93a5b8',
    fontSize: 12,
    paddingHorizontal: 12,
    paddingTop: 10,
  },
  statusBanner: {
    marginHorizontal: 12,
    marginTop: 8,
    backgroundColor: '#92400e',
    borderRadius: 8,
    padding: 10,
  },
  statusText: {color: '#ffffff'},
  messageList: {padding: 12, gap: 8, flexGrow: 1},
  bubble: {borderRadius: 12, padding: 10, maxWidth: '85%'},
  userBubble: {backgroundColor: '#0f766e', alignSelf: 'flex-end'},
  assistantBubble: {backgroundColor: '#ffffff', alignSelf: 'flex-start'},
  userBubbleText: {color: '#ffffff'},
  assistantBubbleText: {color: '#111827'},
  empty: {color: '#93a5b8', textAlign: 'center', marginTop: 40},
  priorityButton: {
    marginHorizontal: 12,
    marginBottom: 8,
    backgroundColor: '#c2410c',
    borderRadius: 10,
    padding: 10,
    alignItems: 'center',
  },
  priorityButtonText: {color: '#ffffff', fontWeight: '700'},
  buttonDisabled: {opacity: 0.5},
  composer: {flexDirection: 'row', gap: 8, padding: 12, alignItems: 'flex-end'},
  input: {
    flex: 1,
    backgroundColor: '#ffffff',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: '#071a2c',
    maxHeight: 120,
  },
  sendButton: {
    backgroundColor: '#0f766e',
    borderRadius: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  sendButtonText: {color: '#ffffff', fontWeight: '700'},
});
