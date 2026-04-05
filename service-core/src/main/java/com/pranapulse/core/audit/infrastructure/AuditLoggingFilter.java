package com.pranapulse.core.audit.infrastructure;

import com.pranapulse.core.audit.application.AuditLogService;
import com.pranapulse.core.auth.repository.UserRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class AuditLoggingFilter extends OncePerRequestFilter {

    private final AuditLogService auditLogService;
    private final UserRepository userRepository;

    public AuditLoggingFilter(
            AuditLogService auditLogService,
            UserRepository userRepository
    ) {
        this.auditLogService = auditLogService;
        this.userRepository = userRepository;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return "/".equals(path)
                || "/health".equals(path)
                || path.startsWith("/actuator")
                || path.startsWith("/api/v1/audit");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        long startedAt = System.currentTimeMillis();
        filterChain.doFilter(request, response);

        try {
            auditLogService.recordHttpEvent(
                    resolveUserId(),
                    request.getMethod() + ":" + request.getRequestURI(),
                    request.getMethod(),
                    request.getRequestURI(),
                    response.getStatus(),
                    (int) (System.currentTimeMillis() - startedAt),
                    extractClientIp(request),
                    request.getHeader("User-Agent"),
                    null
            );
        } catch (Exception ignored) {
            // Audit failures must never break the main request.
        }
    }

    private UUID resolveUserId() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (!(authentication instanceof JwtAuthenticationToken jwtAuthenticationToken)) {
            return null;
        }
        return userRepository.findByOidcSubject(jwtAuthenticationToken.getToken().getSubject())
                .map(user -> user.getId())
                .orElse(null);
    }

    private String extractClientIp(HttpServletRequest request) {
        String forwardedFor = request.getHeader("X-Forwarded-For");
        if (forwardedFor != null && !forwardedFor.isBlank()) {
            return forwardedFor.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }
}
