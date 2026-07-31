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
import {colors, radius, shadow, spacing} from '../ui/theme';

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
      <View style={styles.header}>
        <View style={styles.avatar}>
          <AppText style={styles.avatarText}>AI</AppText>
        </View>
        <View style={styles.headerText}>
          <AppText style={styles.headerTitle}>{t('tab.chat')}</AppText>
          <AppText style={styles.caveat} numberOfLines={2}>
            {t('chat.caveat')}
          </AppText>
        </View>
      </View>

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
          placeholderTextColor={colors.neutral}
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
  page: {flex: 1, backgroundColor: colors.background},
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.lg,
    backgroundColor: colors.surface,
    borderBottomLeftRadius: radius.lg,
    borderBottomRightRadius: radius.lg,
    ...shadow.card,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#D4CEFA',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {color: colors.ink, fontWeight: '800', fontSize: 12},
  headerText: {flex: 1},
  headerTitle: {color: colors.ink, fontWeight: '700', fontSize: 16},
  caveat: {color: colors.inkMuted, fontSize: 11, marginTop: 2},
  statusBanner: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    backgroundColor: '#FFF1E6',
    borderRadius: radius.sm,
    padding: 10,
  },
  statusText: {color: colors.primaryDark},
  messageList: {padding: spacing.lg, gap: spacing.sm, flexGrow: 1},
  bubble: {borderRadius: radius.md, padding: 12, maxWidth: '85%'},
  userBubble: {backgroundColor: colors.primary, alignSelf: 'flex-end', borderBottomRightRadius: 4},
  assistantBubble: {
    backgroundColor: colors.surface,
    alignSelf: 'flex-start',
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: colors.surfaceBorder,
  },
  userBubbleText: {color: colors.surface},
  assistantBubbleText: {color: colors.ink},
  empty: {color: colors.inkMuted, textAlign: 'center', marginTop: 40},
  priorityButton: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.primary,
    borderRadius: radius.pill,
    padding: 10,
    alignItems: 'center',
  },
  priorityButtonText: {color: colors.primaryDark, fontWeight: '700'},
  buttonDisabled: {opacity: 0.5},
  composer: {flexDirection: 'row', gap: spacing.sm, padding: spacing.lg, alignItems: 'flex-end'},
  input: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    paddingVertical: 10,
    color: colors.ink,
    maxHeight: 120,
    borderWidth: 1,
    borderColor: colors.surfaceBorder,
  },
  sendButton: {
    backgroundColor: colors.primary,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    paddingVertical: 12,
  },
  sendButtonText: {color: colors.surface, fontWeight: '700'},
});
