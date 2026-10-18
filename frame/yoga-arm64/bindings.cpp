// The two functions BeatLeader's UI library (Reactive) expects from its yoga.dll on top of Yoga's C API.
// Reactive passes a managed callback that takes an already formatted message:
//   [DllImport("yoga", EntryPoint = "YGBindingsConfigSetLogger")]
//   static extern void YGConfigSetLogger(IntPtr config, YogaLoggerDelegate logger);
//   delegate void YogaLoggerDelegate(LogLevel level, string message);
// Signatures recovered from Reactive.dll's metadata; the upstream DLL ships no source for them.
#include <yoga/Yoga.h>

#include <cstdarg>
#include <cstdio>

using BindingsLogger = void (*)(YGLogLevel level, const char* message);

extern "C" int YGLoggerWrapper(YGConfigConstRef config, YGNodeConstRef, YGLogLevel level, const char* format, va_list args) {
  auto logger = reinterpret_cast<BindingsLogger>(YGConfigGetContext(config));
  if (logger == nullptr) {
    return 0;
  }

  char message[1024];
  int length = vsnprintf(message, sizeof message, format, args);
  logger(level, message);
  return length;
}

// The callback is kept in the config's context pointer, so each config can have its own.
extern "C" void YGBindingsConfigSetLogger(YGConfigRef config, BindingsLogger logger) {
  YGConfigSetContext(config, reinterpret_cast<void*>(logger));
  YGConfigSetLogger(config, logger != nullptr ? &YGLoggerWrapper : nullptr);
}
