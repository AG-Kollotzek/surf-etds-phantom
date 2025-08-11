function tests = test_connection
    tests = functiontests(localfunctions);
end

function testDummy(t)
    % Hier könnte später ein Mock-Port statt echter Hardware genutzt werden.
    verifyTrue(t, true);
end
