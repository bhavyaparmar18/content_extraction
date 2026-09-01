import { useEffect, useState, useRef } from 'react';
import { WorkflowProgressEnvelope } from '@/types';

interface UseWorkflowSocketOptions {
  workflowId?: string;
  onEvent?: (event: WorkflowProgressEnvelope) => void;
}

export function useWorkflowSocket({ workflowId, onEvent }: UseWorkflowSocketOptions) {
  const [latestEvent, setLatestEvent] = useState<WorkflowProgressEnvelope | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!workflowId) {
      setIsConnected(false);
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/workflows/${encodeURIComponent(workflowId)}/progress`;

    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data: WorkflowProgressEnvelope = JSON.parse(event.data);
          setLatestEvent(data);
          onEvent?.(data);
        } catch {
          // Non-JSON message
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
      };

      ws.onerror = () => {
        setIsConnected(false);
      };
    } catch {
      setIsConnected(false);
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [workflowId]);

  return {
    latestEvent,
    isConnected,
  };
}
