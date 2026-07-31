import {
  Text,
  TextInput,
  type TextInputProps,
  type TextProps,
} from 'react-native';

import {useLanguage} from '../i18n/LanguageContext';

/** React Native does not inherit fonts across a View subtree, so every visible
 * text node goes through these wrappers to keep Bangla/English typography
 * consistent. */
export function AppText({style, ...props}: TextProps) {
  const {fontFamily} = useLanguage();
  return <Text {...props} style={[{fontFamily}, style]} />;
}

export function AppTextInput({style, ...props}: TextInputProps) {
  const {fontFamily} = useLanguage();
  return <TextInput {...props} style={[{fontFamily}, style]} />;
}
