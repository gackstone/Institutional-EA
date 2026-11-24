import React, { Component, type ReactNode } from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { DARK_THEME } from "../theme/themeTokens.ts";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onReset?: () => void;
}

interface State {
  hasError: boolean;
  errorMessage: string;
}

export class MobileErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorMessage: error.message || "An unexpected error occurred" };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    // Sanitized logging without leaking trade account secrets
    console.error("[MobileErrorBoundary] Caught UI error:", error.name, error.message);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, errorMessage: "" });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <View style={styles.container}>
          <Text style={styles.title}>Monitoring View Interrupted</Text>
          <Text style={styles.message}>
            {this.state.errorMessage}
          </Text>
          <TouchableOpacity style={styles.button} onPress={this.handleReset}>
            <Text style={styles.buttonText}>Reload View</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: DARK_THEME.background,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
  },
  title: {
    fontSize: 18,
    fontWeight: "700",
    color: DARK_THEME.loss,
    marginBottom: 8,
  },
  message: {
    fontSize: 13,
    color: DARK_THEME.textMuted,
    textAlign: "center",
    marginBottom: 20,
    lineHeight: 18,
  },
  button: {
    backgroundColor: DARK_THEME.accent,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  buttonText: {
    color: "#FFFFFF",
    fontWeight: "600",
    fontSize: 14,
  },
});
