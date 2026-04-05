package com.pranapulse.core.social.application;

import com.pranapulse.core.auth.application.AuthenticatedUserService;
import com.pranapulse.core.auth.domain.User;
import com.pranapulse.core.shared.error.ConflictException;
import com.pranapulse.core.shared.error.NotFoundException;
import com.pranapulse.core.social.domain.SocialConnection;
import com.pranapulse.core.social.repository.SocialConnectionRepository;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SocialConnectionService {

    private final SocialConnectionRepository socialConnectionRepository;
    private final AuthenticatedUserService authenticatedUserService;

    public SocialConnectionService(
            SocialConnectionRepository socialConnectionRepository,
            AuthenticatedUserService authenticatedUserService
    ) {
        this.socialConnectionRepository = socialConnectionRepository;
        this.authenticatedUserService = authenticatedUserService;
    }

    @Transactional(readOnly = true)
    public List<SocialConnection> listConnections(User currentUser) {
        return socialConnectionRepository.findAllForUser(currentUser.getId());
    }

    @Transactional
    public SocialConnection createConnectionRequest(User currentUser, UUID targetUserId) {
        User targetUser = authenticatedUserService.findRequiredUser(targetUserId);
        socialConnectionRepository.findConnectionBetweenUsers(currentUser.getId(), targetUserId)
                .ifPresent(existing -> {
                    throw new ConflictException(
                            "A social connection already exists between these users."
                    );
                });

        SocialConnection connection = new SocialConnection(currentUser, targetUser);
        SocialConnection savedConnection = socialConnectionRepository.save(connection);
        return findRequiredDetailed(savedConnection.getId());
    }

    @Transactional
    public SocialConnection accept(User currentUser, UUID connectionId) {
        SocialConnection connection = findRequired(connectionId);
        connection.accept(currentUser.getId());
        SocialConnection savedConnection = socialConnectionRepository.save(connection);
        return findRequiredDetailed(savedConnection.getId());
    }

    @Transactional
    public SocialConnection decline(User currentUser, UUID connectionId) {
        SocialConnection connection = findRequired(connectionId);
        connection.decline(currentUser.getId());
        SocialConnection savedConnection = socialConnectionRepository.save(connection);
        return findRequiredDetailed(savedConnection.getId());
    }

    private SocialConnection findRequired(UUID connectionId) {
        return socialConnectionRepository.findById(connectionId)
                .orElseThrow(() -> new NotFoundException(
                        "Social connection not found: " + connectionId
                ));
    }

    private SocialConnection findRequiredDetailed(UUID connectionId) {
        return socialConnectionRepository.findDetailedById(connectionId)
                .orElseThrow(() -> new NotFoundException(
                        "Social connection not found: " + connectionId
                ));
    }
}
